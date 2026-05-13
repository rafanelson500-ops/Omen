"""Step 1 — re-run locked IS and OOS backtests with bugfixed features.py.

LOCKED BASELINE PARAMS (NO CHANGES):
  z_threshold        = 1.8
  stop_atr_mult      = 2.0
  target_atr_mult    = 4.5
  time_stop_min      = 25
  blackout_lunch     = True (original lunch blackout, NOT Zach's 12:30 start)
  bar_freq           = 5min
  feature_lookback_bars = 20  (default in BacktestConfig)
  ATR window         = 14     (per features.py hardcoded)

Only the session-boundary fix in features.py has been applied — all other
locked infrastructure is unmodified.

IS window : 2025-12-30 → 2026-04-21 (matches locked_baseline_trades_blackout_lunch.csv)
OOS window: 2025-09-08 → 2025-12-23 (matches oos_baseline_trades_2025-09-08_2025-12-23.csv)
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

ES_PRIMARY = REPO / "backend/data/market/ES_c_0_ohlcv1s_2025-09-08_2026-04-27.parquet"

# Locked params
Z_THRESHOLD = 1.8
BLACKOUT_LUNCH = True
BAR_FREQ = "5min"

WINDOWS = {
    "IS":  (dt.date(2025, 12, 30), dt.date(2026, 4, 21)),
    "OOS": (dt.date(2025, 9, 8),   dt.date(2025, 12, 23)),
}

OUT_DIR = REPO / "diagnostics/session-boundary-bugfix"


def _load_es_1s(start: dt.date, end: dt.date, freq: str = "5min",
                  rth_only: bool = True) -> pd.DataFrame:
    """Load primary ES 1s file and slice/resample to [start, end] RTH."""
    df = pd.read_parquet(ES_PRIMARY)
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


def _run_window(label: str, start: dt.date, end: dt.date) -> pd.DataFrame:
    print("=" * 72)
    print(f"{label} window: {start.isoformat()} → {end.isoformat()}  "
          "(bugfixed features.py)")
    print("=" * 72)
    mkt = _load_es_1s(start, end, freq=BAR_FREQ)
    print(f"  market bars: {len(mkt):,}")

    days = gex.rth_sessions(start, end)
    gex_raw = gex.load_range(days)
    if gex_raw.empty:
        raise RuntimeError("gex.load_range returned empty")
    gex_bars = gex.resample(gex_raw, freq=BAR_FREQ)
    print(f"  GEX bars   : {len(gex_bars):,}")

    feat = features.build_features(mkt, gex_bars)
    # Sanity: ATR shouldn't have huge spikes across session boundaries anymore
    n_huge_atr = int((feat["atr"] > 30).sum())
    print(f"  feature rows: {len(feat):,}  "
          f"bars with ATR>30 (sanity): {n_huge_atr}")

    strat = strategy.FlowBurstStrategy(
        z_threshold=Z_THRESHOLD, blackout_lunch=BLACKOUT_LUNCH,
    )
    signals = strat.signals(feat)
    print(f"  signals fired: {int((signals != 0).sum())} "
          f"(long={int((signals==1).sum())}, short={int((signals==-1).sum())})")

    trades, equity = backtest.run(feat, signals, strategy_name="flow_burst",
                                   cfg=BacktestConfig(bar_freq=BAR_FREQ))
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
    for trades, name in [(is_trades, "locked_baseline_is_bugfixed.csv"),
                          (oos_trades, "oos_baseline_bugfixed.csv")]:
        keep = [c for c in cols_order if c in trades.columns]
        out = OUT_DIR / name
        trades[keep].to_csv(out, index=False)
        print(f"\nSaved: {out}  ({len(trades)} trades)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
