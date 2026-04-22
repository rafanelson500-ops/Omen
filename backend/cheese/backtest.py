"""Event-driven backtester with ATR stops, trailing, time cap, and realistic costs.

Fill conventions:
    - Entries fire at the OPEN of the bar AFTER the signal bar, plus adverse slippage.
    - Stop exits fill at the stop price minus adverse slippage (conservative;
      stops often slip past on fast moves).
    - Target exits are treated as limit orders and fill exactly at target
      (no slippage; limit order didn't have to cross the spread).
    - Time-stop and session-close exits fill at next bar OPEN + adverse slippage.
    - If stop and target are both hit in the same bar, assume stop fills first
      (pessimistic convention).
    - Same-bar entry + stop/target: if the entry bar's H/L already breached the
      stop or target, we close on the entry bar (pessimistic -- stop first if
      both touched). Skipping this check is optimistic because it silently
      assumes adverse same-bar moves didn't exist.

Leakage protections:
    - Entries use signals from bar i-1 and fill at bar i's OPEN. Stops and
      targets are sized from ATR(i-1). Never uses future information.
    - ATR, gamma regime, and flow z-scores are all built from rolling windows
      that only look at past bars (cheese.features).
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import time
from typing import Optional

import numpy as np
import pandas as pd

from cheese.config import (
    BacktestConfig,
    ES_POINT_VALUE,
    ES_TICK_SIZE,
    ES_TICK_VALUE,
    round_to_tick,
)


@dataclass
class Trade:
    strategy: str
    side: int                 # +1 long, -1 short
    entry_time: pd.Timestamp
    entry_px: float
    exit_time: pd.Timestamp
    exit_px: float
    exit_reason: str          # stop | target | time | session_close
    bars_held: int
    stop_px: float
    target_px: float
    atr_at_entry: float
    gamma_regime: str
    gross_points: float
    gross_dollars: float
    cost_dollars: float
    net_dollars: float


def _slippage_points(bars_edge: bool, cfg: BacktestConfig) -> float:
    """Per-side slippage converted into ES points."""
    mult = cfg.cost.edge_slippage_mult if bars_edge else 1.0
    return cfg.cost.slippage_ticks_per_side * mult * ES_TICK_SIZE


def run(
    feat: pd.DataFrame,
    signals: pd.Series,
    strategy_name: str,
    cfg: BacktestConfig = BacktestConfig(),
) -> tuple[pd.DataFrame, pd.Series]:
    """Run backtest. Returns (trades_df, equity_curve_dollars)."""
    if feat.empty:
        return pd.DataFrame(), pd.Series(dtype="float64")

    # We need ATR to be present and signals aligned to feat.
    if "atr" not in feat.columns:
        raise ValueError("feat must contain 'atr' column (build with features.build_features)")
    sig = signals.reindex(feat.index).fillna(0).astype(int)

    o = feat["open"].to_numpy(dtype="float64")
    h = feat["high"].to_numpy(dtype="float64")
    l = feat["low"].to_numpy(dtype="float64")
    c = feat["close"].to_numpy(dtype="float64")
    atr = feat["atr"].to_numpy(dtype="float64")
    regime = feat.get("gamma_regime", pd.Series("unknown", index=feat.index)).to_numpy()
    edge = feat.get("on_session_edge", pd.Series(False, index=feat.index)).to_numpy()
    sig_arr = sig.to_numpy()
    idx = feat.index

    trades: list[Trade] = []
    in_pos = False
    side = 0
    entry_i = -1
    entry_px = stop_px = target_px = 0.0
    atr_entry = 0.0
    trail_armed = False
    regime_entry = "unknown"
    bars_in = 0

    slip_normal = _slippage_points(False, cfg)
    slip_edge = _slippage_points(True, cfg)

    close_time = time(15, 55)

    n = len(feat)
    for i in range(n):
        if in_pos:
            bars_in += 1
            bar_high, bar_low = h[i], l[i]
            # 1R trailing: once 1R in favor, bump stop to breakeven
            if cfg.exits.trail_after_r > 0 and not trail_armed:
                r_move = cfg.exits.stop_atr_mult * atr_entry * cfg.exits.trail_after_r
                if side == 1 and bar_high - entry_px >= r_move:
                    stop_px = round_to_tick(max(stop_px, entry_px))
                    trail_armed = True
                elif side == -1 and entry_px - bar_low >= r_move:
                    stop_px = round_to_tick(min(stop_px, entry_px))
                    trail_armed = True

            exit_reason: Optional[str] = None
            exit_px = np.nan
            stop_hit = (side == 1 and bar_low <= stop_px) or (side == -1 and bar_high >= stop_px)
            tgt_hit = (side == 1 and bar_high >= target_px) or (side == -1 and bar_low <= target_px)

            if stop_hit:
                # pessimistic: stop first; also subtract slip (adverse) on stop
                slip = slip_edge if edge[i] else slip_normal
                exit_px = stop_px - side * slip
                exit_reason = "stop"
            elif tgt_hit:
                exit_px = target_px       # limit fill, no slippage
                exit_reason = "target"

            # time cap (measured in bars; assumes uniform bar freq)
            if exit_reason is None and bars_in >= _bars_for_minutes(cfg.exits.time_stop_min, cfg.bar_freq):
                slip = slip_edge if edge[i] else slip_normal
                # exit at next bar open; but we're evaluating at bar i, so exit at o[i+1] if available else c[i]
                if i + 1 < n:
                    exit_px = o[i + 1] - side * slip
                    exit_reason = "time"
                else:
                    exit_px = c[i] - side * slip
                    exit_reason = "time"

            # force flat at session close
            if exit_reason is None and cfg.exits.close_at_rth_end and idx[i].time() >= close_time:
                slip = slip_edge if edge[i] else slip_normal
                if i + 1 < n and idx[i + 1].date() == idx[i].date():
                    exit_px = o[i + 1] - side * slip
                else:
                    exit_px = c[i] - side * slip
                exit_reason = "session_close"

            if exit_reason is not None:
                # gross_pts already has slippage baked into entry_px and exit_px,
                # so the only *additional* explicit friction is commission.
                # cost_dollars is total friction (commission + slippage) for reporting.
                gross_pts = side * (exit_px - entry_px)
                gross_usd = gross_pts * ES_POINT_VALUE
                commission_usd = 2 * cfg.cost.commission_per_side
                entry_slip_usd = _slippage_points(bool(edge[entry_i]), cfg) * ES_POINT_VALUE
                exit_slip_usd = 0.0 if exit_reason == "target" else _slippage_points(bool(edge[i]), cfg) * ES_POINT_VALUE
                friction_total_usd = commission_usd + entry_slip_usd + exit_slip_usd
                net_usd = gross_usd - commission_usd

                trades.append(
                    Trade(
                        strategy=strategy_name,
                        side=side,
                        entry_time=idx[entry_i],
                        entry_px=float(entry_px),
                        exit_time=idx[i],
                        exit_px=float(exit_px),
                        exit_reason=exit_reason,
                        bars_held=bars_in,
                        stop_px=float(stop_px),
                        target_px=float(target_px),
                        atr_at_entry=float(atr_entry),
                        gamma_regime=str(regime_entry),
                        gross_points=float(gross_pts),
                        gross_dollars=float(gross_usd),
                        cost_dollars=float(friction_total_usd),
                        net_dollars=float(net_usd),
                    )
                )
                in_pos = False
                side = 0
                trail_armed = False
                bars_in = 0

        # entry on signal from PREVIOUS bar (i-1) -> enter at this bar's open
        if not in_pos and i > 0 and sig_arr[i - 1] != 0:
            s = int(sig_arr[i - 1])
            a = atr[i - 1]
            if not np.isnan(a) and a > 0:
                slip = slip_edge if edge[i] else slip_normal
                entry_px = o[i] + s * slip
                stop_px = round_to_tick(entry_px - s * cfg.exits.stop_atr_mult * a)
                target_px = round_to_tick(entry_px + s * cfg.exits.target_atr_mult * a)
                in_pos = True
                side = s
                entry_i = i
                atr_entry = float(a)
                regime_entry = str(regime[i - 1])
                trail_armed = False
                bars_in = 0

                # Same-bar-as-entry check: conservative. If the entry bar's
                # H/L already crossed the stop or target after the open, close
                # on this bar. Stop first when both touched. Without this the
                # backtest is silently optimistic about fast adverse moves.
                bar_high_e, bar_low_e = h[i], l[i]
                stop_hit_e = (s == 1 and bar_low_e <= stop_px) or (s == -1 and bar_high_e >= stop_px)
                tgt_hit_e = (s == 1 and bar_high_e >= target_px) or (s == -1 and bar_low_e <= target_px)
                if stop_hit_e or tgt_hit_e:
                    if stop_hit_e:
                        exit_px_e = stop_px - s * slip
                        exit_reason_e = "stop"
                        exit_slip_usd = _slippage_points(bool(edge[i]), cfg) * ES_POINT_VALUE
                    else:
                        exit_px_e = target_px
                        exit_reason_e = "target"
                        exit_slip_usd = 0.0
                    gross_pts = s * (exit_px_e - entry_px)
                    gross_usd = gross_pts * ES_POINT_VALUE
                    commission_usd = 2 * cfg.cost.commission_per_side
                    entry_slip_usd = _slippage_points(bool(edge[entry_i]), cfg) * ES_POINT_VALUE
                    friction_total_usd = commission_usd + entry_slip_usd + exit_slip_usd
                    net_usd = gross_usd - commission_usd
                    trades.append(
                        Trade(
                            strategy=strategy_name,
                            side=side,
                            entry_time=idx[entry_i],
                            entry_px=float(entry_px),
                            exit_time=idx[i],
                            exit_px=float(exit_px_e),
                            exit_reason=exit_reason_e,
                            bars_held=0,
                            stop_px=float(stop_px),
                            target_px=float(target_px),
                            atr_at_entry=float(atr_entry),
                            gamma_regime=str(regime_entry),
                            gross_points=float(gross_pts),
                            gross_dollars=float(gross_usd),
                            cost_dollars=float(friction_total_usd),
                            net_dollars=float(net_usd),
                        )
                    )
                    in_pos = False
                    side = 0
                    trail_armed = False
                    bars_in = 0

    trades_df = pd.DataFrame([asdict(t) for t in trades])
    equity = _build_equity(idx, trades_df)
    return trades_df, equity


def _bars_for_minutes(minutes: int, bar_freq: str) -> int:
    freq_min = pd.Timedelta(bar_freq).total_seconds() / 60.0
    if freq_min <= 0:
        return minutes
    return max(1, int(round(minutes / freq_min)))


def _build_equity(index: pd.DatetimeIndex, trades: pd.DataFrame) -> pd.Series:
    eq = pd.Series(0.0, index=index)
    if trades.empty:
        return eq.cumsum()
    # attribute each trade's P&L to its exit bar (realized PnL)
    pnl_by_time = trades.groupby("exit_time")["net_dollars"].sum()
    eq.loc[pnl_by_time.index] = pnl_by_time.values
    return eq.cumsum()
