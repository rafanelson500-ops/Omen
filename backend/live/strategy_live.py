"""Live strategy runner.

Architecture
------------
The runner is now **cache-driven**: every 5 seconds it rebuilds the feature
frame from disk (``data/gex/*.parquet`` for orderflow, ``data/market_live/*.parquet``
for ES 1s OHLCV) and fires a ``FlowBurstStrategy`` decision on the most recent
*closed* bar. The disk cache is kept warm by ``scripts/data_daemon.py`` which
runs independently in a screen session -- this guarantees there is no warmup
period on a cold start because the cache already contains 3-5 days of history.

Why not feed the runner directly from the live WebSockets?
* The GEXbot orderflow WS uses a proto schema we don't have (see
  ``live/gexbot_ws.py`` -- the decoded numbers are currently garbage, e.g.
  spot=715141 vs the correct 5910.xx). The REST endpoint (used by the daemon)
  is unambiguous JSON and produces identical fields to the backtester.
* Using the same data layer as the backtester means backtest <-> live
  alignment is exact: same resample, same features.build_features, same
  strategy. No silent divergence.

State machine per trade
-----------------------
    FLAT -> SIGNAL -> SUBMITTED -> FILLED -> (STOP|TARGET|TIME|SESSION) -> FLAT

Once a bracket OSO is accepted the runner considers itself in-position until:
  * a server-side stop/target fill message is observed, OR
  * local time-stop (``time_stop_min``) elapses -> send flatten, OR
  * RTH session close approaches (15:55 ET) -> send flatten.
"""
from __future__ import annotations

import asyncio
import math
import time
from dataclasses import dataclass
from datetime import time as dtime

import pandas as pd

from cheese import features, gex as gex_mod, strategy
from cheese.config import ET, round_to_tick
from live import cache
from live.bus import BUS
from live.logger import get
from live.settings import LiveSettings
from live.tradovate import TradovateClient

log = get("strategy_live")

# How far back to pull from the cache on every tick. Need enough bars at the
# chosen bar_freq for the ATR(14) and flow z-score(60) windows to be fully
# warmed. Generous by design -- reads are cheap (parquet + tz-convert).
LOOKBACK = {
    "1min": pd.Timedelta(hours=12),
    "5min": pd.Timedelta(hours=72),
}

# Minimum bars required for the flow z-score rolling window to produce a valid
# z (matches `features.FLOW_Z_WINDOW // 3` = 20). Until the cache has at least
# this many 5-min GEX bars the strategy is effectively "warming up" and cannot
# fire. The dashboard uses this to render a hydration progress bar.
HYDRATION_TARGET_5M_BARS = 20


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

    # ---------- run loop --------------------------------------------------
    async def run(self) -> None:
        """Strategy loop. Bus events are no longer consumed directly -- the
        runner pulls from the on-disk cache populated by ``data_daemon.py``.
        We still start alongside the rest of the live app so we can react to
        the ARM toggle and submit bracket orders through Tradovate.
        """
        log.info(
            f"strategy runner starting (cache-driven); bar_freq={self.s.bar_freq} "
            f"z={self.s.z_threshold} stop_atr={self.s.stop_atr_mult} "
            f"tgt_atr={self.s.target_atr_mult} time_stop={self.s.time_stop_min}m"
        )
        await BUS.publish("status", {"component": "strategy", "ok": True,
                                     "armed": self._armed, "dry_run": self.s.dry_run})
        # NOTE: do NOT swallow CancelledError here. The supervised() wrapper in
        # run_live.py relies on cancellation propagating out so it knows to
        # stop -- if we catch+return, it thinks the coroutine exited cleanly
        # and helpfully restarts the strategy, defeating Ctrl-C shutdown.
        while True:
            await asyncio.sleep(5.0)
            try:
                await self._tick()
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001
                log.error(f"tick error: {e!r}")

    # ---------- tick ------------------------------------------------------
    async def _tick(self) -> None:
        now = pd.Timestamp.now(tz=ET)
        lookback = LOOKBACK.get(self.s.bar_freq, pd.Timedelta(hours=24))
        since = now - lookback

        # --- GEX cache scan (hydration progress) -----------------------
        # Compute this FIRST, before any early-returns on ES data. Pulling
        # the last 5 sessions from the REST-fed parquet cache -- this runs
        # even outside RTH so the dashboard hydration bar reflects the
        # historical cache as soon as the page loads, then keeps climbing
        # as the daemon writes today's bars once the feed opens.
        days = gex_mod.last_n_sessions(5)
        gex_raw_all = gex_mod.load_range(days)
        self._publish_hydration(gex_raw_all, now)

        # --- ES 1s bars from the daemon-written cache ------------------
        mkt_1s = cache.load_market_live(since=since)
        if mkt_1s.empty:
            log.warning(
                "no ES 1s data in cache; is data_daemon.py running? "
                "see scripts/data_daemon.py"
            )
            return
        lag_s = (now - mkt_1s.index.max()).total_seconds()
        if lag_s > 300:  # >5 min stale
            log.warning(f"ES cache is stale by {lag_s:.0f}s; daemon may be down")

        # Resample to strategy freq (right-closed, right-labelled -- matches
        # cheese.market.load so backtest <-> live are aligned).
        mkt = (
            mkt_1s.resample(self.s.bar_freq, label="right", closed="right")
                  .agg({"open": "first", "high": "max", "low": "min",
                        "close": "last", "volume": "sum"})
                  .dropna(subset=["close"])
        )
        # CRITICAL: drop the partial/unclosed last bar. Pandas resample with
        # label="right" emits a bar whose label is in the future relative to
        # the 1s data timestamp, so the last bar's H/L/C are incomplete.
        # Including it would cause the live strategy to fire on different z
        # values than the backtester (which sees only closed bars).
        mkt = mkt[mkt.index <= now]
        if len(mkt) < 20:
            return

        # Scope the GEX frame for feature building to the strategy lookback.
        gex_raw = gex_raw_all[gex_raw_all.index >= since] if not gex_raw_all.empty else gex_raw_all
        if gex_raw.empty:
            log.warning("no GEX data in cache for the last 5 sessions; is the daemon running?")
            return
        # Numeric-only + same resampler the backtester uses.
        gex_bars = gex_mod.resample(
            gex_raw.select_dtypes(include="number"), freq=self.s.bar_freq,
        )
        gex_bars = gex_bars[gex_bars.index <= now]

        # --- Features + last closed bar --------------------------------
        feat = features.build_features(mkt, gex_bars)
        if feat.empty:
            return
        last = feat.iloc[-1]

        # Publish a compact "now" snapshot for the dashboard
        BUS.publish_nowait("signal", {
            "ts": last.name.isoformat(),
            "close": float(last.get("close", math.nan)),
            "spot": float(last.get("spot", math.nan)) if "spot" in feat.columns else None,
            "gexoflow_z": (float(last.get("gexoflow_z", math.nan))
                           if "gexoflow_z" in feat.columns else None),
            "dexoflow_z": (float(last.get("dexoflow_z", math.nan))
                           if "dexoflow_z" in feat.columns else None),
            "atr": float(last.get("atr", math.nan)),
            "regime": str(last.get("gamma_regime", "?")),
            "position_side": self._position.side,
            "armed": self._armed,
        })

        # --- Position management: time-stop + session close ----------
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

        # --- Entry decision from the most recent CLOSED bar ----------
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

    def _publish_hydration(self, gex_raw: pd.DataFrame, now: pd.Timestamp) -> None:
        """Emit the GEX warmup-progress status used by the dashboard.

        Counts 5-min GEX bars *in the cache* (across the last few sessions),
        not just within the strategy lookback window. This keeps the bar from
        collapsing back to 0 outside RTH when the strategy's short lookback
        excludes the previous session.
        """
        bars_ready = 0
        if gex_raw is not None and not gex_raw.empty:
            try:
                gex_5m = gex_mod.resample(
                    gex_raw.select_dtypes(include="number"), freq="5min",
                )
                gex_5m = gex_5m[gex_5m.index <= now]
                flow_col = next((c for c in ("gexoflow_sum", "gexoflow")
                                 if c in gex_5m.columns), None)
                if flow_col is not None:
                    bars_ready = int(gex_5m[flow_col].dropna().shape[0])
                else:
                    bars_ready = int(len(gex_5m))
            except Exception:  # noqa: BLE001
                bars_ready = 0
        target = HYDRATION_TARGET_5M_BARS
        pct = min(1.0, bars_ready / target) if target else 1.0
        BUS.publish_nowait("status", {
            "component": "gex_hydration",
            "ok": bars_ready >= target,
            "bars": bars_ready,
            "target": target,
            "pct": pct,
        })

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
