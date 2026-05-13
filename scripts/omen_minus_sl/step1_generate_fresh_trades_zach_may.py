"""Step 1 (ZACH'S MAY PARAMS COMPARISON) — same fresh sessions as the
original quick-check, but with an alternative parameter set sourced from
an external spreadsheet.

THROWAWAY COMPARISON. No conclusion about which parameter set is "better"
can be drawn from 18 trades. See SYNTHESIS_zach_may.md for full disclosure.

Parameter overrides (vs the locked baseline):
  z_threshold        : 2.0   (locked = 1.8)
  target_atr_mult    : 5.0   (locked = 4.5)
  time_stop_min      : 35    (locked = 25)
  stop_atr_mult      : 2.0   (locked = 2.0, unchanged)

Held at locked values:
  feature_lookback_bars: 20
  atr_window_bars      : 14 (per locked code default — features.py:54 hardcodes 14)
  trail_after_r        : 0
  blackout_lunch       : True
  bar_freq             : 5min

All overrides happen via dataclass arguments to FlowBurstStrategy + ExitConfig.
No locked files are modified.
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
ES_NEW     = REPO / "backend/data/market/ES_c_0_ohlcv1s_2026-04-28_2026-05-11.parquet"

# Zach's May params
Z_THRESHOLD       = 2.0
STOP_ATR_MULT     = 2.0
TARGET_ATR_MULT   = 5.0
TIME_STOP_MIN     = 35
BLACKOUT_LUNCH    = True
BAR_FREQ          = "5min"

FRESH_DATES = [
    dt.date(2026, 4, 30), dt.date(2026, 5, 1), dt.date(2026, 5, 4),
    dt.date(2026, 5, 5),  dt.date(2026, 5, 6),  dt.date(2026, 5, 7),
    dt.date(2026, 5, 8),  dt.date(2026, 5, 11),
]
WARMUP_START = dt.date(2026, 4, 15)
BACKTEST_END = max(FRESH_DATES)

OUT_DIR = REPO / "analysis/omen-minus-sl-quickcheck"
OUT_CSV = OUT_DIR / "fresh_trades_zach_may.csv"


def _load_es_1s_concat(start: dt.date, end: dt.date, freq: str = "5min",
                        rth_only: bool = True) -> pd.DataFrame:
    df1 = pd.read_parquet(ES_PRIMARY)
    df2 = pd.read_parquet(ES_NEW)
    df = pd.concat([df1, df2])
    df = df[~df.index.duplicated(keep="first")]
    df.index = pd.to_datetime(df.index, utc=True).tz_convert(ET)
    df = df.sort_index()
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
    print("ZACH MAY PARAMS — fresh-session backtest (comparison only)")
    print("=" * 72)
    print(f"  z_threshold       = {Z_THRESHOLD}     (locked=1.8)")
    print(f"  stop_atr_mult     = {STOP_ATR_MULT}   (locked=2.0)")
    print(f"  target_atr_mult   = {TARGET_ATR_MULT} (locked=4.5)")
    print(f"  time_stop_min     = {TIME_STOP_MIN}   (locked=25)")
    print(f"  blackout_lunch    = {BLACKOUT_LUNCH}, bar_freq={BAR_FREQ}")
    print(f"  Fresh sessions    : {len(FRESH_DATES)}\n")

    # Market
    print("Loading ES 1s bars ...")
    mkt = _load_es_1s_concat(WARMUP_START, BACKTEST_END, freq=BAR_FREQ)
    print(f"  market bars: {len(mkt):,}")

    # GEX
    print(f"Loading GEX for [{WARMUP_START}, {BACKTEST_END}] ...")
    days = gex.rth_sessions(WARMUP_START, BACKTEST_END)
    gex_raw = gex.load_range(days)
    if gex_raw.empty:
        print("[FATAL] gex.load_range returned empty.")
        return 1
    gex_bars = gex.resample(gex_raw, freq=BAR_FREQ)

    # Features (locked, ATR=14)
    print("Building features ...")
    feat = features.build_features(mkt, gex_bars)
    print(f"  feature rows: {len(feat):,}")

    # Strategy with Zach z_threshold
    print(f"Running flow_burst with z_threshold={Z_THRESHOLD} (Zach May) ...")
    strat = strategy.FlowBurstStrategy(
        z_threshold=Z_THRESHOLD, blackout_lunch=BLACKOUT_LUNCH,
    )
    signals = strat.signals(feat)
    n_sigs = int((signals != 0).sum())
    print(f"  signals fired: {n_sigs} (long={int((signals==1).sum())}, "
          f"short={int((signals==-1).sum())})")

    # Backtest with Zach exit config
    zach_exits = ExitConfig(
        stop_atr_mult=STOP_ATR_MULT,
        target_atr_mult=TARGET_ATR_MULT,
        time_stop_min=TIME_STOP_MIN,
        # leave atr_window_bars, trail_after_r, close_at_rth_end at locked defaults
    )
    cfg = BacktestConfig(bar_freq=BAR_FREQ, exits=zach_exits)
    print(f"  Backtest cfg: target={cfg.exits.target_atr_mult}×ATR, "
          f"stop={cfg.exits.stop_atr_mult}×ATR, time={cfg.exits.time_stop_min}min")

    trades, equity = backtest.run(feat, signals, strategy_name="flow_burst", cfg=cfg)
    print(f"  TOTAL TRADES IN BACKTEST WINDOW: {len(trades)}")

    # Filter to fresh sessions
    if not trades.empty:
        trades["entry_time"] = pd.to_datetime(trades["entry_time"], utc=True).dt.tz_convert(ET)
        trades["exit_time"] = pd.to_datetime(trades["exit_time"], utc=True).dt.tz_convert(ET)
        trades["hour_min"] = (trades["entry_time"].dt.hour * 60
                              + trades["entry_time"].dt.minute)
        fresh_set = set(FRESH_DATES)
        is_fresh = trades["entry_time"].dt.date.isin(fresh_set)
        fresh_trades = trades[is_fresh].copy()
        print(f"\n  trades in warmup (pre-fresh): {(~is_fresh).sum()}")
        print(f"  trades in fresh sessions    : {len(fresh_trades)}")
    else:
        fresh_trades = trades.copy()

    if len(fresh_trades) > 0:
        fresh_trades["side_label"] = (fresh_trades["side"] == 1).map(
            {True: "LONG", False: "SHORT"}
        )
        fresh_trades["cell"] = (fresh_trades["side_label"] + "_"
                                + fresh_trades["gamma_regime"].astype(str))
        print("\n  Fresh cell breakdown:")
        for c in ["LONG_long", "LONG_short", "SHORT_long", "SHORT_short"]:
            print(f"    {c:<12s} n={int((fresh_trades['cell']==c).sum())}")
        print("\n  Per-session count:")
        for d, n in fresh_trades.groupby(fresh_trades["entry_time"].dt.date).size().items():
            print(f"    {d.isoformat()}  n={n}")
        print("\n  Exit-reason distribution:")
        for r, n in fresh_trades["exit_reason"].value_counts().items():
            print(f"    {r:<14s} n={n}")

    # Save
    cols_order = ["strategy", "side", "contracts", "entry_time", "entry_px",
                  "exit_time", "exit_px", "exit_reason", "bars_held",
                  "stop_px", "target_px", "atr_at_entry", "gamma_regime",
                  "gross_points", "gross_dollars", "cost_dollars",
                  "net_dollars", "hour_min"]
    keep = [c for c in cols_order if c in fresh_trades.columns]
    fresh_trades[keep].to_csv(OUT_CSV, index=False)
    print(f"\nSaved: {OUT_CSV}  ({len(fresh_trades)} trades)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
