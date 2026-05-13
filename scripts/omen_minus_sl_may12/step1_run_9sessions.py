"""Pulse extension — OMEN-minus-SL on 9 fresh sessions (Apr 30 → May 12).

Adds May 12 to the existing 8-session bugfixed quick-check. Bugfixed
infrastructure already on main (features.py session-boundary fix +
backtest.py time-stop + overlap fixes). No infrastructure changes.

Locked baseline params unchanged: z=1.8, blackout_lunch=True,
stop=2.0×ATR, target=4.5×ATR, time_stop=25min, ATR=14, bar_freq=5min.

This is a pulse on partially-consumed data. Pre-reg `9c1c22f` requires
30+ fresh sessions for a verdict; current count is 9.
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
from cheese.config import BacktestConfig  # noqa: E402

ET = ZoneInfo("America/New_York")
ES_FILES = [
    REPO / "backend/data/market/ES_c_0_ohlcv1s_2025-09-08_2026-04-27.parquet",
    REPO / "backend/data/market/ES_c_0_ohlcv1s_2026-04-28_2026-05-11.parquet",
    REPO / "backend/data/market/ES_c_0_ohlcv1s_2026-05-12_2026-05-12.parquet",
]

Z_THRESHOLD = 1.8
BLACKOUT_LUNCH = True
BAR_FREQ = "5min"

FRESH_DATES = [
    dt.date(2026, 4, 30), dt.date(2026, 5, 1), dt.date(2026, 5, 4),
    dt.date(2026, 5, 5),  dt.date(2026, 5, 6),  dt.date(2026, 5, 7),
    dt.date(2026, 5, 8),  dt.date(2026, 5, 11), dt.date(2026, 5, 12),
]
WARMUP_START = dt.date(2026, 4, 15)
BACKTEST_END = max(FRESH_DATES)

OUT_DIR = REPO / "analysis/omen-minus-sl-may12-pulse"
OUT_CSV = OUT_DIR / "fresh_trades_9sessions.csv"


def _load_es_concat(start: dt.date, end: dt.date) -> pd.DataFrame:
    parts = []
    for p in ES_FILES:
        if p.exists():
            parts.append(pd.read_parquet(p))
    df = pd.concat(parts)
    df = df[~df.index.duplicated(keep="first")]
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


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print("=" * 72)
    print("9-session pulse (Apr 30 → May 12) on bugfixed infrastructure")
    print("=" * 72)
    print(f"  ES sources: {len(ES_FILES)} files (concat in-memory)")
    print(f"  Warmup    : {WARMUP_START.isoformat()} → fresh end {BACKTEST_END.isoformat()}")
    print(f"  Fresh sessions: {len(FRESH_DATES)} "
          f"({FRESH_DATES[0].isoformat()} → {FRESH_DATES[-1].isoformat()})")
    print()

    mkt = _load_es_concat(WARMUP_START, BACKTEST_END)
    print(f"  market bars: {len(mkt):,}  ({mkt.index.min()} → {mkt.index.max()})")

    days = gex.rth_sessions(WARMUP_START, BACKTEST_END)
    gex_raw = gex.load_range(days)
    gex_bars = gex.resample(gex_raw, freq=BAR_FREQ)
    print(f"  GEX bars: {len(gex_bars):,}")

    feat = features.build_features(mkt, gex_bars)
    print(f"  feature rows: {len(feat):,}")

    strat = strategy.FlowBurstStrategy(z_threshold=Z_THRESHOLD,
                                        blackout_lunch=BLACKOUT_LUNCH)
    signals = strat.signals(feat)
    print(f"  signals: {int((signals != 0).sum())}")

    trades, equity = backtest.run(feat, signals, strategy_name="flow_burst",
                                   cfg=BacktestConfig(bar_freq=BAR_FREQ))
    print(f"  TOTAL TRADES (warmup + fresh): {len(trades)}")

    if not trades.empty:
        trades["entry_time"] = pd.to_datetime(trades["entry_time"],
                                                utc=True).dt.tz_convert(ET)
        trades["exit_time"] = pd.to_datetime(trades["exit_time"],
                                               utc=True).dt.tz_convert(ET)
        trades["hour_min"] = (trades["entry_time"].dt.hour * 60
                               + trades["entry_time"].dt.minute)
        fresh_set = set(FRESH_DATES)
        is_fresh = trades["entry_time"].dt.date.isin(fresh_set)
        warmup = trades[~is_fresh]
        fresh = trades[is_fresh].copy()
        print(f"\n  warmup trades   : {len(warmup)}")
        print(f"  fresh-session   : {len(fresh)}")

        fresh["side_label"] = (fresh["side"] == 1).map({True: "LONG", False: "SHORT"})
        fresh["cell"] = fresh["side_label"] + "_" + fresh["gamma_regime"].astype(str)
        print("\n  Cell breakdown:")
        for c in ["LONG_long", "LONG_short", "SHORT_long", "SHORT_short"]:
            print(f"    {c:<12s}  n={int((fresh['cell']==c).sum())}")
        print("\n  Per-session count + net $:")
        for d in sorted(fresh["entry_time"].dt.date.unique()):
            sub = fresh[fresh["entry_time"].dt.date == d]
            print(f"    {d.isoformat()}  n={len(sub):>2d}  "
                  f"net=${sub['net_dollars'].sum():>+8.2f}")
        print("\n  May 12 trade detail:")
        may12 = fresh[fresh["entry_time"].dt.date == dt.date(2026, 5, 12)]
        if len(may12) == 0:
            print("    (no trades on May 12)")
        else:
            for _, r in may12.iterrows():
                side = "LONG" if r["side"] == 1 else "SHORT"
                print(f"    {r['entry_time'].strftime('%H:%M')} {side}  "
                      f"regime={r['gamma_regime']}  "
                      f"exit_reason={r['exit_reason']}  "
                      f"entry=${r['entry_px']:.2f}  exit=${r['exit_px']:.2f}  "
                      f"net=${r['net_dollars']:+.2f}")

        print("\n  Exit reason distribution (fresh):")
        for r, n in fresh["exit_reason"].value_counts().items():
            print(f"    {r:<14s} n={n}")
    else:
        fresh = trades.copy()

    cols = ["strategy", "side", "contracts", "entry_time", "entry_px",
            "exit_time", "exit_px", "exit_reason", "bars_held", "stop_px",
            "target_px", "atr_at_entry", "gamma_regime", "gross_points",
            "gross_dollars", "cost_dollars", "net_dollars", "hour_min"]
    keep = [c for c in cols if c in fresh.columns]
    fresh[keep].to_csv(OUT_CSV, index=False)
    print(f"\nSaved: {OUT_CSV} ({len(fresh)} trades)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
