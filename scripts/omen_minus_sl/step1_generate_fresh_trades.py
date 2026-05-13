"""Step 1 — generate OMEN flow_burst trades on the fresh sessions.

THROWAWAY QUICK-CHECK. Uses OMEN's LOCKED backtest infrastructure
(cheese.backtest, cheese.strategy, cheese.features, cheese.gex) via direct
imports — no modifications to that infrastructure.

The only deviation from `run_backtest.py` is that we load ES 1s bars from
the TWO available parquet files (primary 9/8 → 4/27 plus the data-refresh
4/28 → 5/11 file) and concatenate in memory, then resample. This is purely
a market-loader plumbing change forced by how the data refresh kept the
files separate per "never delete existing data files" rule.

Output: analysis/omen-minus-sl-quickcheck/fresh_session_trades_raw.csv
        — schema matches backend/data/analysis/locked_baseline_trades_blackout_lunch.csv
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
from dataclasses import asdict
from datetime import time
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

REPO = Path("/Users/rafanelson/Omen")
sys.path.insert(0, str(REPO / "backend"))

from cheese import backtest, features, gex, strategy  # noqa: E402
from cheese.config import BacktestConfig  # noqa: E402

ET = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")

# Two ES 1s parquet files we need to stitch
ES_PRIMARY = REPO / "backend/data/market/ES_c_0_ohlcv1s_2025-09-08_2026-04-27.parquet"
ES_NEW     = REPO / "backend/data/market/ES_c_0_ohlcv1s_2026-04-28_2026-05-11.parquet"

# Locked baseline parameters (matches PREREG and backend/cheese/config.py defaults)
LOCKED_Z_THRESHOLD = 1.8
LOCKED_BLACKOUT_LUNCH = True
LOCKED_BAR_FREQ = "5min"

# Fresh-session window (May 12 ES bars not yet pulled; user confirmed 9 GEX sessions present)
FRESH_DATES = [
    dt.date(2026, 4, 30), dt.date(2026, 5, 1), dt.date(2026, 5, 4),
    dt.date(2026, 5, 5),  dt.date(2026, 5, 6),  dt.date(2026, 5, 7),
    dt.date(2026, 5, 8),  dt.date(2026, 5, 11),
]
# Backtest start with warmup (need ATR(14) + feature_lookback(20) ≈ 34 bars = ~0.5 sessions)
WARMUP_START = dt.date(2026, 4, 15)
BACKTEST_END = max(FRESH_DATES)

OUT_DIR = REPO / "analysis/omen-minus-sl-quickcheck"
OUT_CSV = OUT_DIR / "fresh_session_trades_raw.csv"


def _load_es_1s_concat(start: dt.date, end: dt.date, freq: str = "5min",
                        rth_only: bool = True) -> pd.DataFrame:
    """Mirror cheese.market.load but pull from the two split parquet files."""
    if not ES_PRIMARY.exists() or not ES_NEW.exists():
        raise FileNotFoundError(
            f"Missing ES 1s parquet(s): primary={ES_PRIMARY.exists()}, "
            f"new={ES_NEW.exists()}"
        )
    df1 = pd.read_parquet(ES_PRIMARY)
    df2 = pd.read_parquet(ES_NEW)
    df = pd.concat([df1, df2])
    df = df[~df.index.duplicated(keep="first")]  # belt-and-braces; no overlap expected
    df.index = pd.to_datetime(df.index, utc=True).tz_convert(ET)
    df = df.sort_index()
    # Date filter on the 1s grid
    start_ts = pd.Timestamp(start, tz=ET)
    end_ts = pd.Timestamp(end + dt.timedelta(days=1), tz=ET)
    df = df[(df.index >= start_ts) & (df.index < end_ts)]
    if rth_only:
        t = df.index.time
        df = df[(t >= time(9, 30)) & (t < time(16, 0))]
    if freq != "1s":
        df = (df.resample(freq, label="right", closed="right")
                .agg({"open": "first", "high": "max", "low": "min",
                       "close": "last", "volume": "sum"})
                .dropna(subset=["close"]))
        t = df.index.time
        df = df[(t > time(9, 30)) & (t <= time(16, 0))]
    return df


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print("=" * 72)
    print("STEP 1 — Fresh-session trade generation (OMEN locked baseline)")
    print("=" * 72)
    print(f"  Locked params: flow_burst z={LOCKED_Z_THRESHOLD}, blackout_lunch=True,")
    print(f"                 bar_freq={LOCKED_BAR_FREQ}, default ExitConfig "
          f"(stop=2.0×ATR, target=4.5×ATR, time=25min, ATR_window=14)")
    print(f"  Warmup start  : {WARMUP_START.isoformat()}")
    print(f"  Backtest end  : {BACKTEST_END.isoformat()}")
    print(f"  Fresh sessions: {len(FRESH_DATES)} "
          f"({FRESH_DATES[0].isoformat()} → {FRESH_DATES[-1].isoformat()})")
    print()

    # ---- Market ----
    print(f"Loading ES 1s bars (concat of two files) ...")
    mkt = _load_es_1s_concat(WARMUP_START, BACKTEST_END, freq=LOCKED_BAR_FREQ)
    print(f"  market bars  : {len(mkt):,} ({mkt.index.min()} → {mkt.index.max()})")

    # ---- GEX ----
    print(f"Loading GEX for [{WARMUP_START}, {BACKTEST_END}] ...")
    days = gex.rth_sessions(WARMUP_START, BACKTEST_END)
    gex_raw = gex.load_range(days)
    if gex_raw.empty:
        print("[FATAL] gex.load_range returned empty.")
        return 1
    gex_bars = gex.resample(gex_raw, freq=LOCKED_BAR_FREQ)
    print(f"  GEX rows raw : {len(gex_raw):,}")
    print(f"  GEX bars     : {len(gex_bars):,}")

    # ---- Features ----
    print("Building features (cheese.features.build_features) ...")
    feat = features.build_features(mkt, gex_bars)
    print(f"  feature rows : {len(feat):,}  cols={len(feat.columns)}")

    # ---- Signals + backtest ----
    print(f"Running flow_burst strategy with locked params ...")
    strat = strategy.FlowBurstStrategy(
        z_threshold=LOCKED_Z_THRESHOLD,
        blackout_lunch=LOCKED_BLACKOUT_LUNCH,
    )
    signals = strat.signals(feat)
    trades, equity = backtest.run(
        feat, signals,
        strategy_name="flow_burst",
        cfg=BacktestConfig(bar_freq=LOCKED_BAR_FREQ),
    )
    print(f"  TOTAL TRADES IN BACKTEST WINDOW: {len(trades)}")

    if len(trades) == 0:
        print("[WARN] backtest produced 0 trades over the warmup+fresh range.")

    # ---- Filter to fresh sessions only ----
    if not trades.empty:
        trades["entry_time"] = pd.to_datetime(trades["entry_time"], utc=True).dt.tz_convert(ET)
        trades["exit_time"]  = pd.to_datetime(trades["exit_time"], utc=True).dt.tz_convert(ET)
        # hour_min schema column (matches locked baseline CSV)
        trades["hour_min"] = (trades["entry_time"].dt.hour * 60
                              + trades["entry_time"].dt.minute)
        # Filter to fresh sessions (>= first fresh date)
        fresh_set = set(FRESH_DATES)
        is_fresh = trades["entry_time"].dt.date.isin(fresh_set)
        warmup_trades = trades[~is_fresh].copy()
        fresh_trades = trades[is_fresh].copy()
        print(f"\n  trades in warmup (pre-{FRESH_DATES[0].isoformat()}): {len(warmup_trades)}")
        print(f"  trades in fresh sessions                : {len(fresh_trades)}")
    else:
        fresh_trades = trades.copy()

    # ---- Per-cell breakdown of fresh trades ----
    if len(fresh_trades) > 0:
        fresh_trades["side_label"] = (fresh_trades["side"] == 1).map(
            {True: "LONG", False: "SHORT"}
        )
        fresh_trades["cell"] = (fresh_trades["side_label"] + "_"
                                + fresh_trades["gamma_regime"].astype(str))
        print("\n  Fresh-session breakdown by cell:")
        bc = fresh_trades.groupby("cell").size().reindex(
            ["LONG_long", "LONG_short", "SHORT_long", "SHORT_short"], fill_value=0
        )
        for cell, n in bc.items():
            print(f"    {cell:<12s}  n={n}")
        print(f"\n  Per-session count:")
        bd = fresh_trades.groupby(fresh_trades["entry_time"].dt.date).size()
        for d, n in bd.items():
            print(f"    {d.isoformat()}  n={n}")

    # ---- Save ----
    # Match locked baseline schema order
    cols_order = [
        "strategy", "side", "contracts", "entry_time", "entry_px",
        "exit_time", "exit_px", "exit_reason", "bars_held", "stop_px",
        "target_px", "atr_at_entry", "gamma_regime", "gross_points",
        "gross_dollars", "cost_dollars", "net_dollars", "hour_min",
    ]
    keep = [c for c in cols_order if c in fresh_trades.columns]
    fresh_trades[keep].to_csv(OUT_CSV, index=False)
    print(f"\nSaved: {OUT_CSV}  ({len(fresh_trades)} trades)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
