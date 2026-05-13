"""Step 1 (ATR=20 SENSITIVITY VARIANT) — same OMEN backtest as the original
quick-check, but with the ATR rolling window switched from 14 → 20.

THROWAWAY SENSITIVITY CHECK. Identical to step1_generate_fresh_trades.py
except for ONE change: after `features.build_features` returns, we overwrite
the `atr` and `atr_pts` columns with SMA(20) instead of the locked SMA(14).
The override is external — no locked files are modified.

Rationale: backend/cheese/features.py:54 hardcodes `tr.rolling(14, min_periods=5).mean()`,
and backend/cheese/backtest.py:85 reads `feat["atr"]` directly. So the cleanest
sensitivity test is to compute SMA(20) on the same True Range series and
substitute it into the same column the backtester reads.

Output: analysis/omen-minus-sl-quickcheck/fresh_session_trades_atr20_raw.csv
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

# Two ES 1s parquet files
ES_PRIMARY = REPO / "backend/data/market/ES_c_0_ohlcv1s_2025-09-08_2026-04-27.parquet"
ES_NEW     = REPO / "backend/data/market/ES_c_0_ohlcv1s_2026-04-28_2026-05-11.parquet"

# Locked baseline parameters — same as ATR=14 variant
LOCKED_Z_THRESHOLD = 1.8
LOCKED_BLACKOUT_LUNCH = True
LOCKED_BAR_FREQ = "5min"

# *** SENSITIVITY KNOB: ATR window changed from 14 → 20 ***
ATR_WINDOW = 20
ATR_MIN_PERIODS = 5

# Same fresh-session window as ATR=14 variant
FRESH_DATES = [
    dt.date(2026, 4, 30), dt.date(2026, 5, 1), dt.date(2026, 5, 4),
    dt.date(2026, 5, 5),  dt.date(2026, 5, 6),  dt.date(2026, 5, 7),
    dt.date(2026, 5, 8),  dt.date(2026, 5, 11),
]
# Slightly longer warmup since ATR(20) needs more bars to stabilize than ATR(14)
WARMUP_START = dt.date(2026, 4, 8)
BACKTEST_END = max(FRESH_DATES)

OUT_DIR = REPO / "analysis/omen-minus-sl-quickcheck"
OUT_CSV = OUT_DIR / "fresh_session_trades_atr20_raw.csv"


def _load_es_1s_concat(start: dt.date, end: dt.date, freq: str = "5min",
                        rth_only: bool = True) -> pd.DataFrame:
    """Concat the two split ES 1s files; resample to `freq` RTH-only."""
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


def _override_atr_window(feat: pd.DataFrame, window: int,
                          min_periods: int) -> pd.DataFrame:
    """Recompute `atr` / `atr_pts` using SMA(window) on the same TR series
    that features.py constructs at line 54. Identical formula except for
    the window. No other columns touched.
    """
    h = feat["high"]; l = feat["low"]; c = feat["close"]
    pc = c.shift(1)
    tr = pd.concat([(h - l), (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    new_atr = tr.rolling(window, min_periods=min_periods).mean()
    feat = feat.copy()
    feat["atr"] = new_atr
    feat["atr_pts"] = new_atr
    return feat


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print("=" * 72)
    print("STEP 1 (ATR=20 SENSITIVITY) — Fresh-session trades, ATR_WINDOW=20")
    print("=" * 72)
    print(f"  Locked params: flow_burst z={LOCKED_Z_THRESHOLD}, blackout_lunch=True,")
    print(f"                 bar_freq={LOCKED_BAR_FREQ}, default ExitConfig "
          "(stop=2.0×ATR, target=4.5×ATR, time=25min)")
    print(f"  *** SENSITIVITY KNOB: ATR_WINDOW = {ATR_WINDOW} "
          f"(min_periods={ATR_MIN_PERIODS}) ***")
    print(f"  Warmup start  : {WARMUP_START.isoformat()} "
          "(extended slightly vs ATR=14 run)")
    print(f"  Backtest end  : {BACKTEST_END.isoformat()}")
    print(f"  Fresh sessions: {len(FRESH_DATES)}\n")

    # ---- Market ----
    print("Loading ES 1s bars (concat of two files) ...")
    mkt = _load_es_1s_concat(WARMUP_START, BACKTEST_END, freq=LOCKED_BAR_FREQ)
    print(f"  market bars: {len(mkt):,}")

    # ---- GEX ----
    print(f"Loading GEX for [{WARMUP_START}, {BACKTEST_END}] ...")
    days = gex.rth_sessions(WARMUP_START, BACKTEST_END)
    gex_raw = gex.load_range(days)
    if gex_raw.empty:
        print("[FATAL] gex.load_range returned empty.")
        return 1
    gex_bars = gex.resample(gex_raw, freq=LOCKED_BAR_FREQ)
    print(f"  GEX bars: {len(gex_bars):,}")

    # ---- Features (locked) + ATR override ----
    print("Building features ...")
    feat = features.build_features(mkt, gex_bars)
    print(f"  feature rows: {len(feat):,}  cols={len(feat.columns)}")
    print(f"  ATR(14) median value (locked): {feat['atr'].median():.4f}")
    feat = _override_atr_window(feat, window=ATR_WINDOW, min_periods=ATR_MIN_PERIODS)
    print(f"  ATR({ATR_WINDOW}) median value (override): {feat['atr'].median():.4f}")

    # ---- Signals + backtest ----
    print(f"Running flow_burst with ATR_WINDOW={ATR_WINDOW} ...")
    strat = strategy.FlowBurstStrategy(
        z_threshold=LOCKED_Z_THRESHOLD, blackout_lunch=LOCKED_BLACKOUT_LUNCH,
    )
    signals = strat.signals(feat)
    trades, equity = backtest.run(
        feat, signals, strategy_name="flow_burst",
        cfg=BacktestConfig(bar_freq=LOCKED_BAR_FREQ),
    )
    print(f"  TOTAL TRADES IN BACKTEST WINDOW: {len(trades)}")

    # ---- Filter to fresh sessions ----
    if not trades.empty:
        trades["entry_time"] = pd.to_datetime(trades["entry_time"], utc=True).dt.tz_convert(ET)
        trades["exit_time"] = pd.to_datetime(trades["exit_time"], utc=True).dt.tz_convert(ET)
        trades["hour_min"] = (trades["entry_time"].dt.hour * 60
                              + trades["entry_time"].dt.minute)
        fresh_set = set(FRESH_DATES)
        is_fresh = trades["entry_time"].dt.date.isin(fresh_set)
        fresh_trades = trades[is_fresh].copy()
        print(f"\n  trades in fresh sessions: {len(fresh_trades)}")
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
        bd = fresh_trades.groupby(fresh_trades["entry_time"].dt.date).size()
        for d, n in bd.items():
            print(f"    {d.isoformat()}  n={n}")

    # ---- Save (locked baseline schema) ----
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
