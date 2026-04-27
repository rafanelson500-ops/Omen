"""Flow Burst dry-run signal logger (forward-test).

Standalone, broker-free. Reads the same on-disk caches as
``live/strategy_live.py`` (kept warm by ``scripts/data_daemon.py``)
and writes one CSV per ET session date under ``data/forward_test/``.

Uses the locked Flow Burst params from ``.env`` and the backtester's
exit precedence + ``CostModel`` so the log is directly comparable to
backtest output.

Two-row CSV encoding: one ``signal`` row per detected signal (filtered
or fired) and one ``exit`` row when a fired signal exits. Joinable by
``signal_time_et``.

Operational note: requires ``scripts/data_daemon.py`` to be running.

Usage:
    python scripts/run_dry_logger.py             # live tick loop
    python scripts/run_dry_logger.py --smoke     # start, probe caches, exit
"""
from __future__ import annotations

import argparse
import csv
import math
import os
import signal as _signal
import sys
import time
from dataclasses import dataclass, field
from datetime import time as dtime
from pathlib import Path
from typing import Optional

import pandas as pd
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cheese import features, gex as gex_mod, strategy
from cheese.config import (
    DATA_DIR,
    ET,
    INSTRUMENTS,
    CostModel,
    round_to_tick,
)
from live import cache, settings as settings_mod
from live.logger import get

log = get("dry_logger")

TICK_INTERVAL_S = 5.0
LOOKBACK = {"1min": pd.Timedelta(hours=12), "5min": pd.Timedelta(hours=72)}
MKT_BARS_MIN = 20
SESSION_CLOSE_T = dtime(15, 55)
RTH_OPEN_T = dtime(9, 30)
SESSION_END_T = dtime(16, 0)

FORWARD_TEST_DIR = DATA_DIR / "forward_test"

CSV_COLUMNS = [
    "row_type",
    "session_date",
    "signal_time_et",
    "entry_time_et",
    "side",
    "gexoflow_z",
    "dexoflow_z",
    "atr",
    "gamma_regime",
    "spot",
    "entry_price",
    "stop_price",
    "target_price",
    "entry_bar_high",
    "entry_bar_low",
    "filtered",
    "filter_reason",
    "hypothetical_exit_time_et",
    "hypothetical_exit_price",
    "hypothetical_exit_reason",
    "hypothetical_bars_held",
    "hypothetical_gross_points",
    "hypothetical_gross_dollars",
    "hypothetical_cost_dollars",
    "hypothetical_net_dollars",
    "quantity",
]


# ---------- helpers ---------------------------------------------------------
def _bool_env(name: str, default: bool) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in {"1", "true", "yes", "on", "y"}


def _bars_for_minutes(minutes: int, bar_freq: str) -> int:
    """Inline copy of cheese.backtest._bars_for_minutes (private)."""
    freq_min = pd.Timedelta(bar_freq).total_seconds() / 60.0
    if freq_min <= 0:
        return minutes
    return max(1, int(round(minutes / freq_min)))


def _on_session_edge(ts: pd.Timestamp) -> bool:
    """Match cheese.gex.resample's on_session_edge: first 15min and last 15min of RTH."""
    m = ts.hour * 60 + ts.minute
    return ((9 * 60 + 30) <= m < (9 * 60 + 45)) or ((15 * 60 + 45) <= m <= (16 * 60))


def _is_lunch(ts: pd.Timestamp) -> bool:
    m = ts.hour * 60 + ts.minute
    return (10 * 60 + 30) <= m < (12 * 60 + 30)


def _rth_open_for_entries(now: pd.Timestamp, bar_freq: str, time_stop_min: int) -> bool:
    """Mirror live.strategy_live._rth_open_for_entries / backtest min_bars_runway."""
    if now.tzinfo is None or now.dayofweek >= 5:
        return False
    if now.time() < RTH_OPEN_T:
        return False
    bar_min = pd.Timedelta(bar_freq).total_seconds() / 60.0
    if bar_min <= 0:
        return False
    max_bars = max(1, int(round(time_stop_min / bar_min)))
    required_minutes = (max_bars + 1) * bar_min
    close_dt = now.normalize() + pd.Timedelta(hours=16)
    minutes_left = (close_dt - now).total_seconds() / 60.0
    return minutes_left >= required_minutes


def _slip_points(on_edge: bool, cost: CostModel, tick_size: float) -> float:
    mult = cost.edge_slippage_mult if on_edge else 1.0
    return cost.slippage_ticks_per_side * mult * tick_size


# ---------- state -----------------------------------------------------------
@dataclass
class Pending:
    """A signal whose entry bar has not yet closed."""
    signal_time: pd.Timestamp
    side: int
    snapshot: pd.Series   # signal-bar feature row (for ROW 1 fields)


@dataclass
class HypoPosition:
    signal_time: pd.Timestamp
    entry_bar_label: pd.Timestamp
    side: int
    entry_price: float
    stop_price: float
    target_price: float
    atr_at_entry: float
    entry_edge: bool
    bars_held: int = 0
    deferred_exit: Optional[str] = None       # "time" or "session_close"
    deferred_exit_bar: Optional[pd.Timestamp] = None  # bar where the trigger fired


@dataclass
class Cfg:
    bar_freq: str
    z_threshold: float
    stop_atr_mult: float
    target_atr_mult: float
    time_stop_min: int
    blackout_lunch: bool
    instrument: str
    quantity: int
    cost: CostModel
    @property
    def bar_width(self) -> pd.Timedelta:
        return pd.Timedelta(self.bar_freq)
    @property
    def tick_size(self) -> float:
        return INSTRUMENTS[self.instrument].tick_size
    @property
    def point_value(self) -> float:
        return INSTRUMENTS[self.instrument].point_value


class DryLogger:
    def __init__(self, cfg: Cfg) -> None:
        self.cfg = cfg
        self.cursor: Optional[pd.Timestamp] = None
        self.pending: Optional[Pending] = None
        self.position: Optional[HypoPosition] = None
        self._csv_path_today: Optional[Path] = None

    # -- IO ----------------------------------------------------------------
    def _csv_path_for(self, ts: pd.Timestamp) -> Path:
        return FORWARD_TEST_DIR / f"{ts.date().isoformat()}_signals.csv"

    def _append_row(self, row: dict) -> None:
        path = self._csv_path_for(pd.Timestamp(row["signal_time_et"]))
        write_header = not path.exists()
        with path.open("a", newline="") as f:
            w = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
            if write_header:
                w.writeheader()
            w.writerow({k: row.get(k, "") for k in CSV_COLUMNS})
            f.flush()

    # -- feature build (mirror strategy_live._tick) ------------------------
    def _build_feat(self) -> pd.DataFrame:
        now = pd.Timestamp.now(tz=ET)
        lookback = LOOKBACK.get(self.cfg.bar_freq, pd.Timedelta(hours=24))
        since = now - lookback

        days = gex_mod.last_n_sessions(5)
        gex_raw = gex_mod.load_range(days)
        gex_in = gex_raw[gex_raw.index >= since] if not gex_raw.empty else gex_raw

        mkt_1s = cache.load_market_live(since=since)
        if mkt_1s.empty:
            return pd.DataFrame()

        mkt = (
            mkt_1s.resample(self.cfg.bar_freq, label="right", closed="right")
            .agg({"open": "first", "high": "max", "low": "min",
                  "close": "last", "volume": "sum"})
            .dropna(subset=["close"])
        )
        mkt = mkt[mkt.index <= now]   # drop partial last bar (live parity)

        if gex_in.empty:
            return pd.DataFrame()
        gex_bars = gex_mod.resample(
            gex_in.select_dtypes(include="number"), freq=self.cfg.bar_freq
        )
        gex_bars = gex_bars[gex_bars.index <= now]
        feat = features.build_features(mkt, gex_bars)
        if len(mkt) < MKT_BARS_MIN or feat.empty:
            return pd.DataFrame()
        return feat

    # -- main entry --------------------------------------------------------
    def tick(self) -> None:
        feat = self._build_feat()
        if feat.empty:
            return

        if self.cursor is None:
            # First tick: anchor at latest closed bar; do not back-process history.
            self.cursor = feat.index[-1]
            return

        new_bars = feat.loc[feat.index > self.cursor]
        for bar_label, bar in new_bars.iterrows():
            self._process_bar(feat, bar_label, bar)
            self.cursor = bar_label

        # Wall-clock safety net: if we're past 16:00 ET and still holding a
        # position (e.g. deferred exit never got its next bar), close at last
        # known close to avoid a stuck open trade in the log.
        now = pd.Timestamp.now(tz=ET)
        if (
            self.position is not None
            and now.time() >= SESSION_END_T
            and now.dayofweek < 5
            and self.position.signal_time.date() == now.date()
        ):
            last_label = feat.index[-1]
            last_close = float(feat["close"].iloc[-1])
            self._emit_exit(
                self.position, last_label, last_close, "session_close",
                trigger_bar=last_label,
            )
            self.position = None

    # -- per-bar processing ------------------------------------------------
    def _process_bar(self, feat: pd.DataFrame, bar_label: pd.Timestamp, bar: pd.Series) -> None:
        # 1) deferred exit from previous bar (time / session_close fills at next bar's open)
        if self.position is not None and self.position.deferred_exit is not None:
            self._fill_deferred_exit(bar_label, bar)
            # NOTE: position cleared inside _fill_deferred_exit; fall through
        # 2) live position: stop > target > time > session_close on this bar's H/L
        if self.position is not None:
            self._step_position(bar_label, bar)
        # 3) pending entry: if this is the entry bar, fill it
        if self.pending is not None:
            expected = self.pending.signal_time + self.cfg.bar_width
            if bar_label == expected:
                self._fire_entry(bar_label, bar)
            elif bar_label > expected:
                log.warning(
                    f"entry bar {expected} missing in cache; dropping pending signal "
                    f"@ {self.pending.signal_time}"
                )
                self.pending = None
        # 4) detect a new signal on this bar
        self._maybe_emit_signal(feat, bar_label, bar)

    # -- signal detection --------------------------------------------------
    def _maybe_emit_signal(
        self, feat: pd.DataFrame, bar_label: pd.Timestamp, bar: pd.Series,
    ) -> None:
        # Run strategy with blackout=False so we see ALL candidates; we apply
        # the lunch filter ourselves below for filter_reason logging.
        strat = strategy.FlowBurstStrategy(
            z_threshold=self.cfg.z_threshold, blackout_lunch=False,
        )
        sigs = strat.signals(feat)
        if bar_label not in sigs.index:
            return
        side = int(sigs.loc[bar_label])
        if side == 0:
            return

        now = pd.Timestamp.now(tz=ET)
        filter_reason = ""
        if self.cfg.blackout_lunch and _is_lunch(bar_label):
            filter_reason = "lunch_blackout"
        elif self.position is not None or self.pending is not None:
            filter_reason = "in_position"
        elif not _rth_open_for_entries(now, self.cfg.bar_freq, self.cfg.time_stop_min):
            filter_reason = "runway_gate"

        # Console line at signal-fire time
        gz = float(bar.get("gexoflow_z", math.nan))
        dz = float(bar.get("dexoflow_z", math.nan))
        atr = float(bar.get("atr", math.nan))
        sclose = float(bar.get("close", math.nan))
        if filter_reason:
            print(
                f"{bar_label.strftime('%Y-%m-%d %H:%M:%S')} ET  "
                f"SIG {side:+d} FILTERED ({filter_reason})  "
                f"z={gz:.2f}  dz={dz:.2f}"
            )
            self._write_filtered_signal_row(bar_label, side, bar, filter_reason)
            return

        print(
            f"{bar_label.strftime('%Y-%m-%d %H:%M:%S')} ET  "
            f"SIG {side:+d}  z={gz:.2f}  dz={dz:.2f}  atr={atr:.2f}  "
            f"signal_close={sclose:.2f}  (waiting for entry bar)"
        )
        self.pending = Pending(signal_time=bar_label, side=side, snapshot=bar.copy())

    def _write_filtered_signal_row(
        self,
        bar_label: pd.Timestamp,
        side: int,
        bar: pd.Series,
        reason: str,
    ) -> None:
        atr = float(bar.get("atr", math.nan))
        sclose = float(bar.get("close", math.nan))
        # entry/stop/target shown as live-runner approximation for analyst convenience.
        # Backtester-style values can be re-derived from the market cache at analysis time.
        if not math.isnan(atr) and not math.isnan(sclose):
            if side == 1:
                stop = round_to_tick(
                    sclose - self.cfg.stop_atr_mult * atr, self.cfg.tick_size
                )
                tgt = round_to_tick(
                    sclose + self.cfg.target_atr_mult * atr, self.cfg.tick_size
                )
            else:
                stop = round_to_tick(
                    sclose + self.cfg.stop_atr_mult * atr, self.cfg.tick_size
                )
                tgt = round_to_tick(
                    sclose - self.cfg.target_atr_mult * atr, self.cfg.tick_size
                )
        else:
            stop = ""
            tgt = ""
        row = {
            "row_type": "signal",
            "session_date": bar_label.date().isoformat(),
            "signal_time_et": bar_label.isoformat(),
            "entry_time_et": "",
            "side": side,
            "gexoflow_z": float(bar.get("gexoflow_z", math.nan)),
            "dexoflow_z": float(bar.get("dexoflow_z", math.nan)),
            "atr": atr,
            "gamma_regime": str(bar.get("gamma_regime", "")),
            "spot": float(bar.get("spot", math.nan)) if "spot" in bar.index else "",
            "entry_price": "",   # filtered: no entry occurs
            "stop_price": stop,
            "target_price": tgt,
            "entry_bar_high": "",
            "entry_bar_low": "",
            "filtered": True,
            "filter_reason": reason,
            "quantity": self.cfg.quantity,
        }
        self._append_row(row)

    # -- entry-bar fill ----------------------------------------------------
    def _fire_entry(self, bar_label: pd.Timestamp, bar: pd.Series) -> None:
        assert self.pending is not None
        side = self.pending.side
        sig_snap = self.pending.snapshot
        atr = float(sig_snap.get("atr", math.nan))
        if math.isnan(atr) or atr <= 0:
            log.warning(
                f"ATR invalid at signal {self.pending.signal_time}; dropping pending"
            )
            self.pending = None
            return

        entry_bar_open = float(bar["open"])
        entry_bar_high = float(bar["high"])
        entry_bar_low = float(bar["low"])
        entry_edge = _on_session_edge(bar_label)
        slip = _slip_points(entry_edge, self.cfg.cost, self.cfg.tick_size)

        entry_price = entry_bar_open + side * slip
        if side == 1:
            stop_px = round_to_tick(
                entry_price - self.cfg.stop_atr_mult * atr, self.cfg.tick_size
            )
            tgt_px = round_to_tick(
                entry_price + self.cfg.target_atr_mult * atr, self.cfg.tick_size
            )
        else:
            stop_px = round_to_tick(
                entry_price + self.cfg.stop_atr_mult * atr, self.cfg.tick_size
            )
            tgt_px = round_to_tick(
                entry_price - self.cfg.target_atr_mult * atr, self.cfg.tick_size
            )

        # Write ROW 1 (signal-fire row, full entry data)
        row = {
            "row_type": "signal",
            "session_date": self.pending.signal_time.date().isoformat(),
            "signal_time_et": self.pending.signal_time.isoformat(),
            "entry_time_et": self.pending.signal_time.isoformat(),  # backtest convention
            "side": side,
            "gexoflow_z": float(sig_snap.get("gexoflow_z", math.nan)),
            "dexoflow_z": float(sig_snap.get("dexoflow_z", math.nan)),
            "atr": atr,
            "gamma_regime": str(sig_snap.get("gamma_regime", "")),
            "spot": float(sig_snap.get("spot", math.nan)) if "spot" in sig_snap.index else "",
            "entry_price": float(entry_price),
            "stop_price": float(stop_px),
            "target_price": float(tgt_px),
            "entry_bar_high": entry_bar_high,
            "entry_bar_low": entry_bar_low,
            "filtered": False,
            "filter_reason": "",
            "quantity": self.cfg.quantity,
        }
        self._append_row(row)

        print(
            f"{bar_label.strftime('%Y-%m-%d %H:%M:%S')} ET  "
            f"ENTRY {side:+d}  px={entry_price:.2f}  stop={stop_px:.2f}  "
            f"tgt={tgt_px:.2f}  atr={atr:.2f}"
        )

        # Same-bar entry exit check (mirror backtest.py:271-320, stop-first)
        if side == 1:
            stop_hit_e = entry_bar_low <= stop_px
            tgt_hit_e = entry_bar_high >= tgt_px
        else:
            stop_hit_e = entry_bar_high >= stop_px
            tgt_hit_e = entry_bar_low <= tgt_px

        # Build provisional position (cleared before exit if same-bar fires)
        pos = HypoPosition(
            signal_time=self.pending.signal_time,
            entry_bar_label=bar_label,
            side=side,
            entry_price=float(entry_price),
            stop_price=float(stop_px),
            target_price=float(tgt_px),
            atr_at_entry=atr,
            entry_edge=entry_edge,
        )
        self.pending = None

        if stop_hit_e or tgt_hit_e:
            if stop_hit_e:
                exit_px = stop_px - side * slip       # same-edge slip on exit
                exit_reason = "stop"
            else:
                exit_px = tgt_px                       # limit fill, no slip
                exit_reason = "target"
            self._emit_exit(pos, bar_label, exit_px, exit_reason, trigger_bar=bar_label)
            return

        self.position = pos

    # -- in-position step --------------------------------------------------
    def _step_position(self, bar_label: pd.Timestamp, bar: pd.Series) -> None:
        pos = self.position
        if pos is None or bar_label == pos.entry_bar_label:
            return  # entry bar handled separately
        pos.bars_held += 1

        bar_high, bar_low = float(bar["high"]), float(bar["low"])
        if pos.side == 1:
            stop_hit = bar_low <= pos.stop_price
            tgt_hit = bar_high >= pos.target_price
        else:
            stop_hit = bar_high >= pos.stop_price
            tgt_hit = bar_low <= pos.target_price

        if stop_hit:
            on_edge = _on_session_edge(bar_label)
            slip = _slip_points(on_edge, self.cfg.cost, self.cfg.tick_size)
            exit_px = pos.stop_price - pos.side * slip
            self._emit_exit(pos, bar_label, exit_px, "stop", trigger_bar=bar_label)
            self.position = None
            return
        if tgt_hit:
            self._emit_exit(pos, bar_label, pos.target_price, "target", trigger_bar=bar_label)
            self.position = None
            return

        # time-stop: bars_held >= max_bars → fill at NEXT bar's open
        max_bars = _bars_for_minutes(self.cfg.time_stop_min, self.cfg.bar_freq)
        if pos.bars_held >= max_bars:
            pos.deferred_exit = "time"
            pos.deferred_exit_bar = bar_label
            return

        # session_close: bar_label.time() >= 15:55 → fill at NEXT bar's open
        if bar_label.time() >= SESSION_CLOSE_T:
            pos.deferred_exit = "session_close"
            pos.deferred_exit_bar = bar_label

    def _fill_deferred_exit(self, bar_label: pd.Timestamp, bar: pd.Series) -> None:
        pos = self.position
        assert pos is not None and pos.deferred_exit is not None
        # bar is the bar AFTER the trigger; fill at its open with slip from trigger bar
        on_edge = _on_session_edge(pos.deferred_exit_bar)
        slip = _slip_points(on_edge, self.cfg.cost, self.cfg.tick_size)
        exit_px = float(bar["open"]) - pos.side * slip
        self._emit_exit(
            pos, bar_label, exit_px, pos.deferred_exit,
            trigger_bar=pos.deferred_exit_bar,
        )
        self.position = None

    # -- exit emission -----------------------------------------------------
    def _emit_exit(
        self,
        pos: HypoPosition,
        exit_bar_label: pd.Timestamp,
        exit_px: float,
        exit_reason: str,
        *,
        trigger_bar: pd.Timestamp,
    ) -> None:
        contracts = self.cfg.quantity
        pt_val = self.cfg.point_value
        gross_pts = pos.side * (exit_px - pos.entry_price)
        gross_usd = gross_pts * pt_val * contracts

        # Friction calc mirrors backtest.py:184-191
        commission_usd = 2 * self.cfg.cost.commission_per_side * contracts
        entry_slip_usd = (
            _slip_points(pos.entry_edge, self.cfg.cost, self.cfg.tick_size)
            * pt_val * contracts
        )
        if exit_reason == "target":
            exit_slip_usd = 0.0
        else:
            exit_slip_usd = (
                _slip_points(_on_session_edge(trigger_bar), self.cfg.cost, self.cfg.tick_size)
                * pt_val * contracts
            )
        friction_total_usd = commission_usd + entry_slip_usd + exit_slip_usd
        net_usd = gross_usd - commission_usd

        # bars_held: backtest computes (exit_fill_ts - entry_fill_ts)/bar_width
        # entry_fill_ts = entry_bar_label - bar_width = signal_time
        # exit_fill_ts = exit_bar_label - bar_width  (for stop/target on bar i)
        #              = exit_bar_label              (for time/session, fills at next bar's open)
        if exit_reason in ("time", "session_close"):
            exit_fill_ts = exit_bar_label   # equivalent to (next_bar - bar_width)
        else:
            exit_fill_ts = exit_bar_label - self.cfg.bar_width
        entry_fill_ts = pos.signal_time
        bars_held_out = int(round((exit_fill_ts - entry_fill_ts) / self.cfg.bar_width))

        row = {
            "row_type": "exit",
            "session_date": pos.signal_time.date().isoformat(),
            "signal_time_et": pos.signal_time.isoformat(),
            "side": pos.side,
            "filtered": False,
            "filter_reason": "",
            "hypothetical_exit_time_et": exit_fill_ts.isoformat(),
            "hypothetical_exit_price": float(exit_px),
            "hypothetical_exit_reason": exit_reason,
            "hypothetical_bars_held": bars_held_out,
            "hypothetical_gross_points": float(gross_pts),
            "hypothetical_gross_dollars": float(gross_usd),
            "hypothetical_cost_dollars": float(friction_total_usd),
            "hypothetical_net_dollars": float(net_usd),
            "quantity": self.cfg.quantity,
        }
        self._append_row(row)

        print(
            f"{exit_fill_ts.strftime('%Y-%m-%d %H:%M:%S')} ET  "
            f"EXIT {exit_reason}  px={exit_px:.2f}  net=${net_usd:+,.2f}  "
            f"bars_held={bars_held_out}"
        )


# ---------- entrypoint ------------------------------------------------------
def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--smoke",
        action="store_true",
        help="probe caches and exit; do not enter the tick loop",
    )
    return p.parse_args()


def main() -> None:
    args = _parse_args()
    load_dotenv()
    s = settings_mod.load()

    cfg = Cfg(
        bar_freq=s.bar_freq,
        z_threshold=s.z_threshold,
        stop_atr_mult=s.stop_atr_mult,
        target_atr_mult=s.target_atr_mult,
        time_stop_min=s.time_stop_min,
        blackout_lunch=_bool_env("LIVE_BLACKOUT_LUNCH", True),
        instrument=s.symbol_root,
        quantity=s.quantity,
        cost=CostModel(),
    )

    inst = INSTRUMENTS.get(cfg.instrument)
    if inst is None:
        print(f"unknown instrument {cfg.instrument!r} — supported: {list(INSTRUMENTS)}")
        sys.exit(2)

    print("=" * 60)
    print("Flow Burst Dry Logger — loaded params")
    print("=" * 60)
    print(f"  bar_freq         : {cfg.bar_freq}")
    print(f"  z_threshold      : {cfg.z_threshold}")
    print(f"  stop_atr_mult    : {cfg.stop_atr_mult}")
    print(f"  target_atr_mult  : {cfg.target_atr_mult}")
    print(f"  time_stop_min    : {cfg.time_stop_min}")
    print(f"  blackout_lunch   : {cfg.blackout_lunch}")
    print(f"  instrument       : {cfg.instrument} "
          f"(point_value={inst.point_value}, tick_size={inst.tick_size})")
    print(f"  quantity         : {cfg.quantity}")
    print(f"  cost.commission  : ${cfg.cost.commission_per_side}/side")
    print(f"  cost.slip_ticks  : {cfg.cost.slippage_ticks_per_side} ticks/side "
          f"(edge mult x{cfg.cost.edge_slippage_mult})")
    print()

    print("Probing caches…")
    try:
        days = gex_mod.last_n_sessions(5)
        gx = gex_mod.load_range(days)
        if days:
            print(f"  GEX cache         : {len(gx):,} 1s rows across "
                  f"{len(days)} sessions ({days[0]} → {days[-1]})")
        else:
            print(f"  GEX cache         : no recent sessions")
    except Exception as e:  # noqa: BLE001
        print(f"  GEX cache         : ERROR {e!r}")
        sys.exit(2)
    try:
        mk = cache.load_market_live(
            since=pd.Timestamp.now(tz=ET) - pd.Timedelta(hours=2)
        )
        print(f"  market_live cache : {len(mk):,} 1s rows in last 2h")
    except Exception as e:  # noqa: BLE001
        print(f"  market_live cache : ERROR {e!r}")
        sys.exit(2)

    FORWARD_TEST_DIR.mkdir(parents=True, exist_ok=True)
    print(f"  output dir        : {FORWARD_TEST_DIR}")
    print()

    if args.smoke:
        print("Smoke test mode: caches readable, params loaded. Exiting cleanly.")
        return

    print(f"Starting tick loop ({TICK_INTERVAL_S:.0f}s interval). Ctrl-C to exit.")
    print()

    logger = DryLogger(cfg)
    stopped = {"flag": False}

    def _sig(*_a):
        if not stopped["flag"]:
            stopped["flag"] = True
            print("\n[shutdown] signal received; finishing current tick and exiting…")

    _signal.signal(_signal.SIGINT, _sig)
    _signal.signal(_signal.SIGTERM, _sig)

    while not stopped["flag"]:
        try:
            logger.tick()
        except Exception as e:  # noqa: BLE001
            log.error(f"tick error: {e!r}")
        # Sleep responsively
        end = time.monotonic() + TICK_INTERVAL_S
        while not stopped["flag"] and time.monotonic() < end:
            time.sleep(0.1)

    print("[shutdown] complete.")


if __name__ == "__main__":
    main()
