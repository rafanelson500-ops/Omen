"""Step 1 — run Zach's full Omen 2.0 parameter set on IS and OOS.

Uses the bugfixed infrastructure already on main (features.py session-boundary
fix + backtest.py time-stop & overlap fixes). No infrastructure changes.

Zach's full parameter set (vs locked):
  Strategy:
    z_threshold       = 2.0      (locked 1.8)
    blackout_lunch    = False    (locked True — replaced by TRADE_START_TIME)
    TRADE_START_TIME  = 12:30 ET (signal filter; no entries before 12:30)
  ExitConfig:
    stop_atr_mult     = 1.5      (locked 2.0)
    target_atr_mult   = 2.5      (locked 4.5)
    trail_after_r     = 1.0      (locked 0 — trailing stop ON)
    time_stop_min     = 30       (locked 25)
    atr_window_bars   = 14       (same; informational only — features.py uses 14)
  BacktestConfig:
    feature_lookback_bars = 60   (informational; features.py FLOW_Z_WINDOW=60 already)
    bar_freq          = 5min     (same)

TRADE_START_TIME is implemented as a signal filter — any signal at a bar with
close-time before 12:30 ET is zeroed out (entry fills at signal_bar_close, so
allowed entries are at bars with close >= 12:30 ET).
"""
from __future__ import annotations

import datetime as dt
import sys
from datetime import time
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

REPO = Path("/Users/rafanelson/Omen")
sys.path.insert(0, str(REPO / "backend"))

from cheese import backtest, features, gex, strategy  # noqa: E402
from cheese.config import BacktestConfig, ExitConfig  # noqa: E402

ET = ZoneInfo("America/New_York")
ES_PRIMARY = REPO / "backend/data/market/ES_c_0_ohlcv1s_2025-09-08_2026-04-27.parquet"

# Zach Omen 2.0 params
Z_THRESHOLD = 2.0
BLACKOUT_LUNCH = False
TRADE_START_TIME = time(12, 30)
STOP_ATR_MULT = 1.5
TARGET_ATR_MULT = 2.5
TRAIL_AFTER_R = 1.0
TIME_STOP_MIN = 30
BAR_FREQ = "5min"

WINDOWS = {
    "IS":  (dt.date(2025, 12, 30), dt.date(2026, 4, 21)),
    "OOS": (dt.date(2025, 9, 8),   dt.date(2025, 12, 23)),
}

OUT_DIR = REPO / "analysis/zach-omen2"


def _load_es_1s(start: dt.date, end: dt.date) -> pd.DataFrame:
    df = pd.read_parquet(ES_PRIMARY)
    df.index = pd.to_datetime(df.index, utc=True).tz_convert(ET)
    df = df.sort_index()
    start_ts = pd.Timestamp(start, tz=ET)
    end_ts = pd.Timestamp(end + dt.timedelta(days=1), tz=ET)
    df = df[(df.index >= start_ts) & (df.index < end_ts)]
    t = df.index.time
    df = df[(t >= time(9, 30)) & (t < time(16, 0))]
    df = (df.resample(BAR_FREQ, label="right", closed="right")
            .agg({"open": "first", "high": "max", "low": "min",
                   "close": "last", "volume": "sum"})
            .dropna(subset=["close"]))
    t = df.index.time
    df = df[(t > time(9, 30)) & (t <= time(16, 0))]
    return df


def _run_window(label: str, start: dt.date, end: dt.date) -> pd.DataFrame:
    print("=" * 72)
    print(f"{label}: {start.isoformat()} → {end.isoformat()}  (ZACH OMEN 2.0)")
    print("=" * 72)
    mkt = _load_es_1s(start, end)
    days = gex.rth_sessions(start, end)
    gex_raw = gex.load_range(days)
    gex_bars = gex.resample(gex_raw, freq=BAR_FREQ)
    feat = features.build_features(mkt, gex_bars)
    print(f"  feature rows: {len(feat):,}")

    # Strategy — no lunch blackout (Zach removed it)
    strat = strategy.FlowBurstStrategy(z_threshold=Z_THRESHOLD,
                                        blackout_lunch=BLACKOUT_LUNCH)
    signals = strat.signals(feat)
    raw_count = int((signals != 0).sum())
    print(f"  raw signals (before TRADE_START_TIME filter): {raw_count}")

    # TRADE_START_TIME filter — zero out signals where bar close < 12:30 ET
    # Signal at bar i fires entry filling at idx[i]'s close time (entry_fill_t).
    # Allowed: signal_bar_close >= 12:30 ET → entries from 12:30 onwards.
    bar_times = signals.index.time
    pre_open_mask = pd.Series([t < TRADE_START_TIME for t in bar_times],
                                index=signals.index)
    signals = signals.where(~pre_open_mask, 0)
    filtered_count = int((signals != 0).sum())
    dropped = raw_count - filtered_count
    print(f"  signals after 12:30 ET filter: {filtered_count} "
          f"(dropped {dropped} pre-12:30 signals)")

    # ExitConfig — Zach's exit params
    zach_exits = ExitConfig(
        stop_atr_mult=STOP_ATR_MULT,
        target_atr_mult=TARGET_ATR_MULT,
        trail_after_r=TRAIL_AFTER_R,
        time_stop_min=TIME_STOP_MIN,
        # atr_window_bars and close_at_rth_end at locked defaults
    )
    cfg = BacktestConfig(bar_freq=BAR_FREQ, exits=zach_exits)
    print(f"  exits: stop={cfg.exits.stop_atr_mult}×ATR, "
          f"target={cfg.exits.target_atr_mult}×ATR, "
          f"trail_after_r={cfg.exits.trail_after_r}, "
          f"time_stop={cfg.exits.time_stop_min}min")

    trades, equity = backtest.run(feat, signals, strategy_name="flow_burst",
                                   cfg=cfg)
    print(f"  trades: {len(trades)}")

    if len(trades) > 0:
        trades["entry_time"] = pd.to_datetime(trades["entry_time"],
                                                utc=True).dt.tz_convert(ET)
        trades["exit_time"] = pd.to_datetime(trades["exit_time"],
                                               utc=True).dt.tz_convert(ET)
        trades["hour_min"] = (trades["entry_time"].dt.hour * 60
                               + trades["entry_time"].dt.minute)
    return trades


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    is_trades = _run_window("IS", *WINDOWS["IS"])
    oos_trades = _run_window("OOS", *WINDOWS["OOS"])
    cols_order = ["strategy", "side", "contracts", "entry_time", "entry_px",
                  "exit_time", "exit_px", "exit_reason", "bars_held",
                  "stop_px", "target_px", "atr_at_entry", "gamma_regime",
                  "gross_points", "gross_dollars", "cost_dollars",
                  "net_dollars", "hour_min"]
    for trades, name in [(is_trades, "zach_is_trades.csv"),
                          (oos_trades, "zach_oos_trades.csv")]:
        out = OUT_DIR / name
        trades[[c for c in cols_order if c in trades.columns]].to_csv(out, index=False)
        print(f"\nSaved: {out}  ({len(trades)} trades)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
