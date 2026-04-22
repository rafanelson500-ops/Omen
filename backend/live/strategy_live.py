"""Live strategy runner.

Consumes price + flow events from the bus, rebuilds rolling bars at the chosen
frequency, computes the same features as the backtester, fires flow_burst
signals, and submits bracket orders through Tradovate.

State machine per trade:
    FLAT -> SIGNAL -> SUBMITTED -> FILLED -> (STOP|TARGET|TIME|SESSION) -> FLAT

For simplicity, once a bracket OSO is accepted, the runner considers itself
'in position' until either:
  * a server-side stop/target fill message is observed, OR
  * local time-stop (`time_stop_min`) elapses -> send flatten, OR
  * RTH session close approaches (15:55 ET) -> send flatten.
"""
from __future__ import annotations

import asyncio
import math
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, time as dtime, timezone
from typing import Any

import pandas as pd

from cheese import features, strategy
from cheese.config import round_to_tick
from live.bus import BUS, Event
from live.logger import get
from live.settings import LiveSettings
from live.tradovate import TradovateClient

log = get("strategy_live")

ET_OFFSET_HOURS = -4  # approx; strategy uses 'America/New_York' timezone-aware stamps

# How many seconds to keep in each rolling buffer (we need enough for ATR(14)
# + flow z-score window, at the bar frequency).
BUFFER_SECONDS = {
    "1min": 60 * 60 * 3,   # 3h of 1s data -> 180 bars after resample
    "5min": 60 * 60 * 12,  # 12h -> 144 bars
}


@dataclass
class PositionState:
    side: int = 0                 # +1 long, -1 short, 0 flat
    entry_time: float = 0.0       # epoch seconds
    entry_px: float = 0.0
    stop_px: float = 0.0
    target_px: float = 0.0
    qty: int = 0
    submitted: bool = False       # order submitted, not yet confirmed filled


class StrategyRunner:
    def __init__(self, settings: LiveSettings, tradovate: TradovateClient,
                 contract: dict) -> None:
        self.s = settings
        self.tv = tradovate
        self.contract = contract
        self._es_1s: deque[dict] = deque(maxlen=BUFFER_SECONDS.get(settings.bar_freq, 3600))
        self._gex_1s: deque[dict] = deque(maxlen=BUFFER_SECONDS.get(settings.bar_freq, 3600))
        self._position = PositionState()
        self._armed: bool = not settings.dry_run   # mirrored to dashboard toggle
        self._last_signal_time: float = 0.0
        self._strategy = strategy.FlowBurstStrategy(z_threshold=settings.z_threshold)

    # ---------- armed toggle ---------------------------------------------
    @property
    def armed(self) -> bool:
        return self._armed

    def set_armed(self, flag: bool) -> None:
        self._armed = flag
        log.warning(f"ARMED={flag}")
        BUS.publish_nowait("status", {"component": "strategy", "ok": True, "armed": flag,
                                      "dry_run": self.s.dry_run})

    # ---------- bus consumer --------------------------------------------
    async def run(self) -> None:
        q = await BUS.subscribe(queue_size=4096)
        tick_task = asyncio.create_task(self._tick_loop())
        try:
            while True:
                ev: Event = await q.get()
                if ev.ch == "price" and ev.data.get("src") == "databento":
                    self._on_price(ev.data)
                elif ev.ch == "flow" and ev.data.get("src") == "gexbot":
                    self._on_flow(ev.data)
        except asyncio.CancelledError:
            tick_task.cancel()
            raise

    def _on_price(self, d: dict) -> None:
        # Normalize ES timestamps to ET so GEX (ET) and ES (UTC from Databento) align
        ts = pd.Timestamp(d["ts"])
        if ts.tzinfo is None:
            ts = ts.tz_localize("UTC")
        ts = ts.tz_convert("America/New_York")
        self._es_1s.append({
            "ts": ts,
            "open": d["open"], "high": d["high"], "low": d["low"],
            "close": d["close"], "volume": d["volume"],
        })

    def _on_flow(self, d: dict) -> None:
        # payload shape is whatever gexbot_ws parsed. We try to extract the flat dict.
        payload = d.get("payload") or d.get("args")
        if isinstance(payload, list) and payload:
            payload = payload[0] if isinstance(payload[0], dict) else None
        if not isinstance(payload, dict):
            return
        if "timestamp" not in payload:
            return
        row = dict(payload)
        try:
            ts = pd.to_datetime(row["timestamp"], unit="s", utc=True).tz_convert("America/New_York")
        except Exception:  # noqa: BLE001
            return
        row["ts"] = ts
        self._gex_1s.append(row)

    # ---------- periodic tick --------------------------------------------
    async def _tick_loop(self) -> None:
        """Every 5s: build bars, compute features, decide. Also poll exits."""
        while True:
            try:
                await asyncio.sleep(5.0)
                await self._tick()
            except asyncio.CancelledError:
                return
            except Exception as e:  # noqa: BLE001
                log.error(f"tick error: {e!r}")

    async def _tick(self) -> None:
        now = pd.Timestamp.now(tz="America/New_York")

        # --- Build bars from rolling 1s buffers
        if len(self._es_1s) < 120:  # need at least ~2min of data
            return

        mkt = pd.DataFrame(list(self._es_1s)).set_index("ts").sort_index()
        mkt = (
            mkt.resample(self.s.bar_freq, label="right", closed="right")
               .agg({"open": "first", "high": "max", "low": "min",
                     "close": "last", "volume": "sum"})
               .dropna(subset=["close"])
        )
        if len(mkt) < 20:
            return

        gex_df = pd.DataFrame()
        if self._gex_1s:
            gex_df = pd.DataFrame(list(self._gex_1s)).set_index("ts").sort_index()
            # keep only known numeric columns
            num = gex_df.select_dtypes(include="number")
            from cheese.gex import resample as gex_resample
            gex_df = gex_resample(num, freq=self.s.bar_freq)

        feat = features.build_features(mkt, gex_df)
        last = feat.iloc[-1] if not feat.empty else None
        if last is None:
            return

        # Publish a compact "now" snapshot to dashboard
        BUS.publish_nowait("signal", {
            "ts": last.name.isoformat(),
            "close": float(last.get("close", math.nan)),
            "spot": float(last.get("spot", math.nan)) if "spot" in last else None,
            "gexoflow_z": float(last.get("gexoflow_z", math.nan)) if "gexoflow_z" in last else None,
            "dexoflow_z": float(last.get("dexoflow_z", math.nan)) if "dexoflow_z" in last else None,
            "atr": float(last.get("atr", math.nan)),
            "regime": str(last.get("gamma_regime", "?")),
            "position_side": self._position.side,
            "armed": self._armed,
        })

        # --- Position management: time-stop + session close
        if self._position.side != 0 and self._position.submitted:
            held_min = (time.time() - self._position.entry_time) / 60.0
            if held_min >= self.s.time_stop_min:
                log.warning(f"time-stop hit ({held_min:.1f} min), flattening")
                await self._flatten("time_stop")
                return
            if _rth_close_window(now):
                log.warning("session close window, flattening")
                await self._flatten("session_close")
                return

        # --- Entry decision from the most recent closed bar
        if self._position.side != 0:
            return
        if not _rth_open_for_entries(now):
            return

        sig = self._strategy.signals(feat)
        last_sig = int(sig.iloc[-1] if len(sig) else 0)
        if last_sig == 0:
            return

        # 1-per-bar throttle (avoid re-entry in same bar after flip)
        if time.time() - self._last_signal_time < 30:
            return

        if not self._armed:
            log.info(f"signal {last_sig:+d} suppressed (not armed)")
            BUS.publish_nowait("signal", {
                "ts": last.name.isoformat(), "side": last_sig, "armed": False,
                "gexoflow_z": float(last.get("gexoflow_z", math.nan)),
                "dexoflow_z": float(last.get("dexoflow_z", math.nan)),
            })
            self._last_signal_time = time.time()
            return

        # Compute stop + target from ATR, submit bracket
        atr = float(last["atr"])
        if atr <= 0 or math.isnan(atr):
            log.warning("ATR invalid, skipping entry")
            return
        close_px = float(last["close"])
        if last_sig == 1:
            stop = round_to_tick(close_px - self.s.stop_atr_mult * atr)
            tgt = round_to_tick(close_px + self.s.target_atr_mult * atr)
            side = "Buy"
        else:
            stop = round_to_tick(close_px + self.s.stop_atr_mult * atr)
            tgt = round_to_tick(close_px - self.s.target_atr_mult * atr)
            side = "Sell"

        log.warning(f"SIGNAL {side} {self.s.quantity} @ ~{close_px:.2f} "
                    f"stop={stop:.2f} tgt={tgt:.2f} atr={atr:.2f}")
        self._last_signal_time = time.time()
        self._position = PositionState(side=last_sig, entry_time=time.time(),
                                       entry_px=close_px, stop_px=stop, target_px=tgt,
                                       qty=self.s.quantity, submitted=True)
        BUS.publish_nowait("signal", {
            "ts": last.name.isoformat(), "side": last_sig, "armed": True,
            "entry_px": close_px, "stop_px": stop, "target_px": tgt, "atr": atr,
        })
        try:
            await self.tv.place_bracket_market(self.contract, side, self.s.quantity, stop, tgt)
        except Exception as e:  # noqa: BLE001
            log.error(f"order submission failed: {e!r}")
            self._position = PositionState()  # reset; no exposure

    async def _flatten(self, reason: str) -> None:
        pos = self._position
        if pos.side == 0:
            return
        side_to_close = "Buy" if pos.side == 1 else "Sell"
        try:
            await self.tv.close_position_market(self.contract, side_to_close, pos.qty)
            log.warning(f"flattened due to {reason}")
            BUS.publish_nowait("order", {"src": "local", "event": "flatten", "reason": reason})
        except Exception as e:  # noqa: BLE001
            log.error(f"flatten failed: {e!r}")
        finally:
            self._position = PositionState()


def _rth_open_for_entries(now: pd.Timestamp) -> bool:
    """New entries only between 09:30 and 15:40 ET (20 min buffer before close)."""
    if now.tzinfo is None:
        return False
    t = now.time()
    return dtime(9, 30) <= t <= dtime(15, 40) and now.dayofweek < 5


def _rth_close_window(now: pd.Timestamp) -> bool:
    if now.tzinfo is None:
        return False
    t = now.time()
    return t >= dtime(15, 55) and now.dayofweek < 5
