"""Live strategy runner.

Architecture
------------
The runner is now **cache-driven**: every 5 seconds it rebuilds the feature
frame from disk (``data/gex/*.parquet`` for orderflow, ``data/market_live/*.parquet``
for ES 1s OHLCV) and fires a ``FlowBurstStrategy`` decision on the most recent
*closed* bar. The disk cache is kept warm by ``scripts/data_daemon.py`` (separate process).
A deep on-disk *GEX* history does not help if *ES* 1s has only just started
writing: the feature tiles need both feeds aligned in the lookback. The
*Feature Warmup* progress reflects ES bar count and z-window fill, not GEX
file size alone.

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
import os
import httpx as _httpx
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

# Market bars required before feature building (matches len(mkt) < 20 early-return
# in _tick). At 5min this is ~100 minutes of live ES 1s in the cache; GEX
# file depth alone is NOT sufficient — the old "hydration" counter that only
# counted 5m GEX rows across *historical* files was misleading.
MKT_BARS_MIN = 20


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

        # --- GEX cache (GEX Live Tick panel) -----------------------------
        days = gex_mod.last_n_sessions(5)
        gex_raw_all = gex_mod.load_range(days)
        self._publish_raw_tick(gex_raw_all, now)

        gex_in_lookback = (
            gex_raw_all[gex_raw_all.index >= since] if not gex_raw_all.empty else gex_raw_all
        )

        # --- ES 1s -> strategy bars (same as backtest) -----------------
        mkt_1s = cache.load_market_live(since=since)
        mkt: pd.DataFrame | None = None
        gex_bars: pd.DataFrame | None = None
        feat: pd.DataFrame | None = None

        if mkt_1s.empty:
            self._publish_feature_warmup(
                mkt, gex_in_lookback, feat, now, es_warning=True,
            )
            log.warning(
                "no ES 1s data in cache; is data_daemon.py running? "
                "see scripts/data_daemon.py"
            )
            return

        lag_s = (now - mkt_1s.index.max()).total_seconds()
        if lag_s > 300:  # >5 min stale
            log.warning(f"ES cache is stale by {lag_s:.0f}s; daemon may be down")

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

        if gex_in_lookback.empty:
            self._publish_feature_warmup(
                mkt, gex_in_lookback, None, now, gex_warning=True,
            )
            log.warning("no GEX data in cache for the strategy lookback; is the daemon running?")
            return

        gex_bars = gex_mod.resample(
            gex_in_lookback.select_dtypes(include="number"), freq=self.s.bar_freq,
        )
        gex_bars = gex_bars[gex_bars.index <= now]
        feat = features.build_features(mkt, gex_bars)
        self._publish_feature_warmup(mkt, gex_in_lookback, feat, now)

        if len(mkt) < MKT_BARS_MIN:
            return

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
        if not _rth_open_for_entries(now, self.s.bar_freq, self.s.time_stop_min):
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
        
        from cheese.config import INSTRUMENTS
        inst = INSTRUMENTS.get(self.s.symbol_root, INSTRUMENTS["ES"])
        
        if last_sig == 1:
            stop = round_to_tick(close_px - self.s.stop_atr_mult * atr, inst.tick_size)
            tgt = round_to_tick(close_px + self.s.target_atr_mult * atr, inst.tick_size)
            side = "Buy"
        else:
            stop = round_to_tick(close_px + self.s.stop_atr_mult * atr, inst.tick_size)
            tgt = round_to_tick(close_px - self.s.target_atr_mult * atr, inst.tick_size)
            side = "Sell"

        qty = self.s.quantity
        if self.s.sizing_mode == "kelly":
            try:
                from cheese import backtest
                from cheese.config import BacktestConfig, CostModel, ExitConfig
                cfg = BacktestConfig(
                    bar_freq=self.s.bar_freq,
                    instrument=self.s.symbol_root,
                    sizing_mode="kelly",
                    account_size=self.s.account_size,
                    kelly_fraction=self.s.kelly_fraction,
                    cost=CostModel(),
                    exits=ExitConfig(
                        stop_atr_mult=self.s.stop_atr_mult,
                        target_atr_mult=self.s.target_atr_mult,
                        time_stop_min=self.s.time_stop_min
                    )
                )
                # Run the backtester over the last ~5 days of warmed cache to compute Kelly
                sim_sig = self._strategy.signals(feat)
                tr_df, _ = backtest.run(feat, sim_sig, "flow_burst", cfg)
                
                if not tr_df.empty:
                    net_pnls = tr_df["net_dollars"].tolist()
                    wins = [x for x in net_pnls if x > 0]
                    losses = [x for x in net_pnls if x <= 0]
                    
                    if len(net_pnls) >= 5 and wins and losses:
                        win_rate = len(wins) / len(net_pnls)
                        avg_win = sum(wins) / len(wins)
                        avg_loss = abs(sum(losses) / len(losses))
                        R = avg_win / avg_loss
                        k = win_rate - ((1 - win_rate) / R)
                        k = max(0.0, min(k, 1.0))
                        
                        fractional_k = k * self.s.kelly_fraction
                        if fractional_k > 0:
                            risk_usd = self.s.stop_atr_mult * atr * inst.point_value
                            current_eq = self.s.account_size + sum(net_pnls)
                            if current_eq > 0 and risk_usd > 0:
                                qty = max(1, int((current_eq * fractional_k) / risk_usd))
                    else:
                        log.warning("Not enough simulated trades (min 5) to compute Kelly, defaulting to 1")
                        qty = 1
                else:
                    qty = 1
            except Exception as e:
                log.error(f"Kelly computation failed, defaulting to static: {e!r}")
                qty = self.s.quantity

        log.warning(f"SIGNAL {side} {qty} @ ~{close_px:.2f} "
                    f"stop={stop:.2f} tgt={tgt:.2f} atr={atr:.2f}")
        self._last_signal_time = time.time()
        self._position = PositionState(side=last_sig, entry_time=time.time(),
                                       entry_px=close_px, stop_px=stop, target_px=tgt,
                                       qty=qty, submitted=True)
        BUS.publish_nowait("signal", {
            "ts": last.name.isoformat(), "side": last_sig, "armed": True,
            "entry_px": close_px, "stop_px": stop, "target_px": tgt, "atr": atr, "qty": qty
        })
        try:
            await self.tv.place_bracket_market(
                self.contract, side, qty, stop, tgt
            )
            # Mirror to TradersPost — fire-and-forget,
            # never blocks or fails the main submission.
            tp_action = "buy" if side == "Buy" else "sell"
            tp_ticker = self.contract.get("name", "ES")
            asyncio.create_task(
                self._fire_traderspost_webhook(
                    action=tp_action,
                    ticker=tp_ticker,
                    qty=qty,
                    stop_px=stop,
                    target_px=tgt,
                )
            )
        except Exception as e:  # noqa: BLE001
            log.error(f"order submission failed: {e!r}")
            self._position = PositionState()  # reset; no exposure

    async def _fire_traderspost_webhook(
        self,
        action: str,
        ticker: str,
        qty: int,
        stop_px: float | None = None,
        target_px: float | None = None,
    ) -> None:
        """Mirror trade to TradersPost (prop eval account).
        Failures are logged but NEVER propagate — main
        Tradovate order is unaffected."""
        url = (os.getenv("TRADERSPOST_WEBHOOK_URL", "") or "").strip().strip('"').strip("'")
        if not url:
            log.debug("TRADERSPOST_WEBHOOK_URL not set; skipping mirror")
            return
        # Strip Tradovate contract suffix to root symbol so
        # TradersPost continuous-contract mapping resolves
        # correctly (ESM6 -> ES, MESM6 -> MES).
        root = ticker
        for suffix in ("H6", "M6", "U6", "Z6", "H7", "M7", "U7", "Z7"):
            if root.endswith(suffix):
                root = root[:-2]
                break
        payload: dict = {
            "ticker": root,
            "action": action,
            "quantity": int(qty),
        }
        if stop_px is not None:
            payload["stopLoss"] = {"type": "stop", "stopPrice": round(float(stop_px), 2)}
        if target_px is not None:
            payload["takeProfit"] = {"limitPrice": round(float(target_px), 2)}
        try:
            async with _httpx.AsyncClient(timeout=5.0) as client:
                r = await client.post(url, json=payload)
                if 200 <= r.status_code < 300:
                    log.info(
                        f"TradersPost mirror OK: {action} {qty} {root} "
                        f"stop={stop_px} tgt={target_px} HTTP {r.status_code}"
                    )
                else:
                    log.warning(
                        f"TradersPost mirror non-2xx: HTTP {r.status_code} "
                        f"body={r.text[:300]}"
                    )
        except Exception as e:  # noqa: BLE001
            log.warning(f"TradersPost mirror failed (non-fatal): {e!r}")

    def _publish_feature_warmup(
        self,
        mkt: pd.DataFrame | None,
        gex_in_lookback: pd.DataFrame | None,
        feat: pd.DataFrame | None,
        _now: pd.Timestamp,
        *,
        es_warning: bool = False,
        gex_warning: bool = False,
    ) -> None:
        """Publish a single scalar: progress toward a finite ``gexoflow_z``.

        In ``features.build_features``::

            flow_z_window   = FLOW_Z_WINDOW       (60)
            min_periods     = FLOW_Z_WINDOW // 3  (20)

        pandas rolling().mean()/.std() returns the FIRST finite value at
        row ``min_periods``, NOT at ``window``. The backtester and live
        strategy only ever need ``gexoflow_z`` to be finite on the last
        bar, so the warmup target is **20** aligned feature bars.

        We count ``gexoflow_sum`` rows on the feature frame (those are the
        rows that feed the rolling window, and they only exist once GEX has
        been aligned to an ES bar). This is the same definition the tiles
        consume, so at 100% the tiles are guaranteed to be live.
        """
        _ = mkt, gex_in_lookback  # kept for call-site symmetry

        target = max(features.FLOW_Z_WINDOW // 3, 1)  # = 20 for default 60

        bars = 0
        z_last_ok = False
        if feat is not None and not feat.empty and "gexoflow_sum" in feat.columns:
            bars = int(feat["gexoflow_sum"].notna().sum())
            if "gexoflow_z" in feat.columns and len(feat):
                z_last = float(feat["gexoflow_z"].iloc[-1])
                z_last_ok = not math.isnan(z_last)

        pct = max(0.0, min(1.0, bars / target))
        ok = z_last_ok and bars >= target

        if es_warning:
            detail = "no ES 1s in cache — start scripts/data_daemon.py"
        elif gex_warning:
            detail = "no GEX in lookback — start data_daemon GEX poller"
        elif bars == 0:
            detail = "waiting for aligned GEX rows…"
        elif bars < target:
            remaining = target - bars
            detail = f"{bars}/{target} aligned bars · {remaining} to go"
        elif not z_last_ok:
            detail = (
                f"{bars}/{target} bars · latest bar missing gexoflow_z "
                "(GEX/ES gap on most recent bar)"
            )
        else:
            detail = "warmed · z-score live"

        BUS.publish_nowait("status", {
            "component": "gex_hydration",
            "ok": ok,
            "z_bars": bars,
            "z_target": target,
            "pct": pct,
            "detail": detail,
        })

    def _publish_raw_tick(self, gex_raw: pd.DataFrame, now: pd.Timestamp) -> None:
        """Emit the latest raw GEX cache row on the `gex_raw` bus channel.

        Purely a dashboard sanity indicator -- proves the data_daemon
        -> parquet -> strategy_runner pipeline is actually flowing. Distinct
        from `signal` (which also needs enough ES+GEX history for z-scores).

        Age is computed once here (server-side) and refreshed client-side
        every 500ms off the event's `received_at` so the "Xs ago" number
        actually ticks between the 5s strategy ticks.
        """
        if gex_raw is None or gex_raw.empty:
            BUS.publish_nowait("gex_raw", {"ok": False, "reason": "no_cache"})
            return
        last = gex_raw.iloc[-1]
        ts = gex_raw.index[-1]
        age_s = max(0.0, (now - ts).total_seconds())

        def _num(v):
            try:
                f = float(v)
            except (TypeError, ValueError):
                return None
            return None if math.isnan(f) else f

        BUS.publish_nowait("gex_raw", {
            "ok": True,
            "ts": ts.isoformat(),
            "age_s": age_s,
            "ticker": str(last.get("ticker", "?")),
            "spot": _num(last.get("spot")),
            "gexoflow": _num(last.get("gexoflow")),
            "dexoflow": _num(last.get("dexoflow")),
            "cvroflow": _num(last.get("cvroflow")),
        })

    async def _flatten(self, reason: str) -> None:
        pos = self._position
        if pos.side == 0:
            return
        side_to_close = "Buy" if pos.side == 1 else "Sell"
        try:
            await self.tv.close_position_market(
                self.contract, side_to_close, pos.qty
            )
            log.warning(f"flattened due to {reason}")
            BUS.publish_nowait("order", {
                "src": "local", "event": "flatten",
                "reason": reason,
            })
            # Mirror exit to TradersPost
            tp_ticker = self.contract.get("name", "ES")
            asyncio.create_task(
                self._fire_traderspost_webhook(
                    action="exit",
                    ticker=tp_ticker,
                    qty=pos.qty,
                )
            )
        except Exception as e:  # noqa: BLE001
            log.error(f"flatten failed: {e!r}")
        finally:
            self._position = PositionState()


def _rth_open_for_entries(now: pd.Timestamp, bar_freq: str, time_stop_min: int) -> bool:
    """New entries allowed only when enough session runway remains.

    Mirrors the backtester's end-of-session gate: require ``max_bars + 1`` bar
    periods between ``now`` and the 16:00 ET close, where
    ``max_bars = round(time_stop_min / bar_minutes)``. At 5min/25min this caps
    entries at 15:30 ET; at 1min/25min, 15:34 ET.
    """
    if now.tzinfo is None or now.dayofweek >= 5:
        return False
    if now.time() < dtime(9, 30):
        return False
    bar_min = pd.Timedelta(bar_freq).total_seconds() / 60.0
    if bar_min <= 0:
        return False
    max_bars = max(1, int(round(time_stop_min / bar_min)))
    required_minutes = (max_bars + 1) * bar_min
    close_dt = now.normalize() + pd.Timedelta(hours=16)
    minutes_left = (close_dt - now).total_seconds() / 60.0
    return minutes_left >= required_minutes


def _rth_close_window(now: pd.Timestamp) -> bool:
    if now.tzinfo is None:
        return False
    t = now.time()
    return t >= dtime(15, 55) and now.dayofweek < 5
