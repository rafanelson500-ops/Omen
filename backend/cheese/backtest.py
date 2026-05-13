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
    INSTRUMENTS,
    round_to_tick,
)


@dataclass
class Trade:
    strategy: str
    side: int                 # +1 long, -1 short
    contracts: int
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


def _slippage_points(bars_edge: bool, cfg: BacktestConfig, tk_sz: float) -> float:
    """Per-side slippage converted into points."""
    mult = cfg.cost.edge_slippage_mult if bars_edge else 1.0
    return cfg.cost.slippage_ticks_per_side * mult * tk_sz


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
    contracts = 0
    entry_i = -1
    entry_px = stop_px = target_px = 0.0
    atr_entry = 0.0
    trail_armed = False
    regime_entry = "unknown"
    bars_in = 0

    inst = INSTRUMENTS.get(cfg.instrument, INSTRUMENTS["ES"])
    tk_sz = inst.tick_size
    pt_val = inst.point_value

    slip_normal = _slippage_points(False, cfg, tk_sz)
    slip_edge = _slippage_points(True, cfg, tk_sz)

    # Bars are right-labeled in market.load (label="right", closed="right"), so
    # a bar labeled T covers (T - bar_width, T] and its `open` is at wall-clock
    # T - bar_width. TradingView uses left-labels, so subtracting one bar width
    # gives fill timestamps that line up with what a user sees on the chart.
    bar_width = pd.Timedelta(cfg.bar_freq)

    close_time = time(15, 55)

    n = len(feat)

    # End-of-session entry gate: disallow entries when fewer than
    # (time_stop_bars + 1) bars remain in the session. If time-stop = 5 bars
    # we require 6 bars of runway so the time-stop can fire cleanly before
    # the forced session_close flatten steps on top of it.
    max_bars_per_trade = _bars_for_minutes(cfg.exits.time_stop_min, cfg.bar_freq)
    min_bars_runway = max_bars_per_trade + 1
    # Time-stop trigger threshold. Because exits fill at the NEXT bar's open
    # (a one-bar-width step forward in wall-clock), the trigger must fire
    # one bar EARLIER than the naive "bars elapsed >= max_bars" check, or
    # the realised duration overshoots time_stop_min by exactly one bar.
    # Concretely: time_stop_min=25 with 5min bars => max_bars=5. We want the
    # exit fill to land at o[entry_i + 5] (= entry_open + 25min), which
    # means triggering at iteration entry_i + 4 (bars_in == 4). Using
    # `bars_in >= max_bars` instead would trigger at entry_i + 5 and fill
    # at o[entry_i + 6] => 30min realised, which silently breaks
    # backtest <-> live alignment (the live runner uses wall-clock
    # (now - entry_time) >= time_stop_min, which IS exact).
    # Floored at 1 so degenerate max_bars=1 configs still hold for at least
    # one bar of feedback (full sub-bar exit semantics aren't supported).
    time_stop_trigger = max(1, max_bars_per_trade - 1)
    # bars_left[i] = number of bars in the same calendar session with label >= idx[i]
    dates_arr = np.array([ts.date() for ts in idx])
    bars_left = np.zeros(n, dtype=np.int64)
    for k in range(n - 1, -1, -1):
        if k == n - 1 or dates_arr[k] != dates_arr[k + 1]:
            bars_left[k] = 1
        else:
            bars_left[k] = bars_left[k + 1] + 1
    for i in range(n):
        # When an exit fires at iteration i, we must NOT also enter a new
        # trade in the same iteration. The entry block below uses
        # sig_arr[i - 1] and fills at o[i] (wall-clock idx[i] - bar_width),
        # which is BEFORE the just-resolved exit:
        #   * time / session_close exits fill at o[i + 1] = idx[i]      (≥ o[i])
        #   * stop / target exits fill at stop_px/target_px mid-bar i   (≥ o[i])
        # Allowing the paired same-iteration entry produces a trade whose
        # entry_time predates the prior trade's exit_time -- the textbook
        # overlap visible in the user's 2026-05-11 export (trade #1 enters
        # at 17:15 while trade #0 is still open until 17:20). Live cannot
        # produce that: at the bar boundary it (a) detects/awaits the exit
        # webhook, then (b) evaluates sig of the just-closed bar, and (c)
        # fires the new entry at the boundary, not one bar earlier.
        # Skipping the entry block here defers the new entry to iteration
        # i + 1, where `sig_arr[i]` is the signal of the bar that just
        # closed and `o[i + 1]` is the same wall-clock instant the live
        # runner ticks at -- byte-for-byte aligned.
        exit_occurred = False
        if in_pos:
            bars_in += 1
            bar_high, bar_low = h[i], l[i]
            # 1R trailing: once 1R in favor, bump stop to breakeven
            if cfg.exits.trail_after_r > 0 and not trail_armed:
                r_move = cfg.exits.stop_atr_mult * atr_entry * cfg.exits.trail_after_r
                if side == 1 and bar_high - entry_px >= r_move:
                    stop_px = round_to_tick(max(stop_px, entry_px), tk_sz)
                    trail_armed = True
                elif side == -1 and entry_px - bar_low >= r_move:
                    stop_px = round_to_tick(min(stop_px, entry_px), tk_sz)
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

            # time cap (measured in bars; assumes uniform bar freq).
            # See `time_stop_trigger` comment above for the off-by-one
            # rationale (we trigger one bar early because the fill lands
            # at next-bar-open).
            if exit_reason is None and bars_in >= time_stop_trigger:
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
                gross_usd = gross_pts * pt_val * contracts
                commission_usd = 2 * cfg.cost.commission_per_side * contracts
                entry_slip_usd = _slippage_points(bool(edge[entry_i]), cfg, tk_sz) * pt_val * contracts
                exit_slip_usd = 0.0 if exit_reason == "target" else _slippage_points(bool(edge[i]), cfg, tk_sz) * pt_val * contracts
                friction_total_usd = commission_usd + entry_slip_usd + exit_slip_usd
                net_usd = gross_usd - commission_usd

                # Fill timestamps are the left edge of the bar that actually
                # produced the fill. Stop/target fill mid-bar `i`. Time and
                # session-close exits fill at the *next* bar's open when one
                # exists, so the fill bar is `i + 1` (its left edge == idx[i]).
                entry_fill_ts = idx[entry_i] - bar_width
                if exit_reason in ("time", "session_close") and i + 1 < n:
                    exit_fill_ts = idx[i]              # == idx[i+1] - bar_width
                else:
                    exit_fill_ts = idx[i] - bar_width
                bars_held_out = int(round((exit_fill_ts - entry_fill_ts) / bar_width))

                trades.append(
                    Trade(
                        strategy=strategy_name,
                        side=side,
                        contracts=contracts,
                        entry_time=entry_fill_ts,
                        entry_px=float(entry_px),
                        exit_time=exit_fill_ts,
                        exit_px=float(exit_px),
                        exit_reason=exit_reason,
                        bars_held=bars_held_out,
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
                exit_occurred = True

        # entry on signal from PREVIOUS bar (i-1) -> enter at this bar's open.
        # `exit_occurred` blocks entries on iterations where a prior trade
        # just exited; see the comment at the top of the loop for why.
        if not exit_occurred and not in_pos and i > 0 and sig_arr[i - 1] != 0:
            s = int(sig_arr[i - 1])
            a = atr[i - 1]
            # end-of-session gate: need max_bars + 1 bars of runway (incl. this one)
            if bars_left[i] < min_bars_runway:
                continue
            if not np.isnan(a) and a > 0:
                contracts = cfg.static_quantity
                if cfg.sizing_mode == "kelly" and trades and len(trades) >= 10:
                    net_pnls = [t.net_dollars for t in trades]
                    wins = [x for x in net_pnls if x > 0]
                    losses = [x for x in net_pnls if x <= 0]
                    if wins and losses:
                        win_rate = len(wins) / len(net_pnls)
                        avg_win = sum(wins) / len(wins)
                        avg_loss = abs(sum(losses) / len(losses))
                        R = avg_win / avg_loss
                        k = win_rate - ((1 - win_rate) / R)
                        k = max(0.0, min(k, 1.0))
                        
                        fractional_k = k * cfg.kelly_fraction
                        if fractional_k > 0:
                            risk_pts = cfg.exits.stop_atr_mult * a
                            risk_usd = risk_pts * pt_val
                            current_equity = cfg.account_size + sum(net_pnls)
                            if current_equity > 0 and risk_usd > 0:
                                ideal_contracts = (current_equity * fractional_k) / risk_usd
                                contracts = max(1, int(ideal_contracts))

                slip = slip_edge if edge[i] else slip_normal
                entry_px = o[i] + s * slip
                stop_px = round_to_tick(entry_px - s * cfg.exits.stop_atr_mult * a, tk_sz)
                target_px = round_to_tick(entry_px + s * cfg.exits.target_atr_mult * a, tk_sz)
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
                        exit_slip_usd = _slippage_points(bool(edge[i]), cfg, tk_sz) * pt_val * contracts
                    else:
                        exit_px_e = target_px
                        exit_reason_e = "target"
                        exit_slip_usd = 0.0
                    gross_pts = s * (exit_px_e - entry_px)
                    gross_usd = gross_pts * pt_val * contracts
                    commission_usd = 2 * cfg.cost.commission_per_side * contracts
                    entry_slip_usd = _slippage_points(bool(edge[entry_i]), cfg, tk_sz) * pt_val * contracts
                    friction_total_usd = commission_usd + entry_slip_usd + exit_slip_usd
                    net_usd = gross_usd - commission_usd
                    entry_fill_ts = idx[entry_i] - bar_width
                    exit_fill_ts = entry_fill_ts  # same-bar fill
                    trades.append(
                        Trade(
                            strategy=strategy_name,
                            side=side,
                            contracts=contracts,
                            entry_time=entry_fill_ts,
                            entry_px=float(entry_px),
                            exit_time=exit_fill_ts,
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
    if trades.empty:
        return pd.Series(0.0, index=index).cumsum()
    # attribute each trade's P&L to its exit bar (realized PnL).
    # Exit timestamps are wall-clock fill times (left edge of the fill bar)
    # and may not line up exactly with `index` (e.g. a stop firing on the
    # first RTH bar has exit_time = 09:30, which the RTH filter drops from
    # the feature frame). Union the two indices before assigning so we never
    # KeyError on a legitimate fill.
    pnl_by_time = trades.groupby("exit_time")["net_dollars"].sum()
    combined = index.union(pnl_by_time.index).sort_values()
    eq = pd.Series(0.0, index=combined)
    eq.loc[pnl_by_time.index] = pnl_by_time.values
    return eq.cumsum()
