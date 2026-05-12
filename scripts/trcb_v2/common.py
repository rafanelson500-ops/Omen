"""Shared constants for TRCB-v2 in-sample analysis (THROWAWAY).

CRITICAL: This test is NOT a valid pre-registration. Parameters were chosen
AFTER observing TRCB-v1 post-mortem results on the same 160-session corpus.
See CRITICAL_DISCLOSURE below for full statement.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

# ===== CRITICAL DISCLOSURE (verbatim, must appear in every saved report) =====
CRITICAL_DISCLOSURE = """\
## CRITICAL METHODOLOGICAL DISCLOSURE

This test is NOT a valid pre-registration. The user is running TRCB-v2
on the same 160-session corpus that:
  - TRCB-v1 Phase 2 already consumed
  - Q1/Q2/Q3 post-mortem already analyzed at multiple window lengths
  - Q4 MFE/MAE analysis already consumed
  - Q2 specifically tested the 30s window and showed positive signal

The TRCB-v2 parameters (30s window, 1.5:1 ratio) were chosen AFTER
observing post-mortem results that showed 30s windows produce positive
forward signal. This means the parameter selection was informed by the
data being tested. This is in-sample parameter tuning by definition,
regardless of any pre-registration documentation.

A positive result here does NOT constitute validation of TRCB-v2. It
constitutes evidence that the parameters that already looked good on
this data continue to look good on this data. To validate TRCB-v2, fresh
forward-only sessions must be used in a future test.

A negative result here would be more informative than a positive one —
it would indicate the framework is weaker than the post-mortem suggested.

The user has explicitly overridden methodological objections and is
proceeding with this test knowing the above.
"""

# ===== LOCKED PARAMETERS (TRCB-v2, in-sample) =====
WINDOW_SECONDS = 30        # P1 detection window length (seconds post signal-bar-close)
VOLUME_MULT = 1.0          # P2 directional volume threshold (× trailing-100-bar median)
DELTA_RATIO = 1.5          # P3 directional:opposite aggressive volume ratio
PRICE_ATR_MULT = 0.25      # P4 net signed price move (× ATR_at_entry)
ATR_WINDOW = 14            # ATR lookback in 5-min bars
DIVISOR_FLOOR = 1          # P3 zero-divisor guard
TRAILING_MEDIAN_BARS = 100 # trailing-bar median for P2 baseline

RTH_START = "09:30"
RTH_END = "16:00"
TIMEZONE = "America/New_York"

BAR_FREQ = "5min"
BAR_FREQ_SECONDS = 300

# Multi-horizon forward-return horizons (minutes)
FORWARD_HORIZONS_MIN = [1, 5, 15, 25]

# ===== Paths =====
REPO = Path("/Users/rafanelson/Omen")
MBP10_DIR = Path("/Users/rafanelson/Library/Caches/omen-pipeline-synthesis/mbp10_cache")
ES_1S_PATH = REPO / "backend/data/market/ES_c_0_ohlcv1s_2025-09-08_2026-04-27.parquet"

IS_TRADE_LOG_PATH = REPO / "backend/data/analysis/locked_baseline_trades_blackout_lunch.csv"
OOS_TRADE_LOG_PATH = REPO / "backend/data/analysis/oos_baseline_trades_2025-09-08_2025-12-23.csv"

# v1 Phase 2 reference (for comparison)
V1_PHASE2_CSV = REPO / "diagnostics/mbp10-trcb-v1/phase2_population_results.csv"

OUTPUT_DIAG_DIR = REPO / "diagnostics/trcb-v2-consumed"
OUTPUT_ANALYSIS_DIR = REPO / "analysis/trcb-v2-consumed"

PER_BAR_VOLUMES_PATH = OUTPUT_DIAG_DIR / "per_bar_volumes_30s.parquet"
PHASE2_RESULTS_CSV = OUTPUT_ANALYSIS_DIR / "phase2_population_results.csv"
PHASE2_REPORT_MD = OUTPUT_ANALYSIS_DIR / "phase2_summary_report.md"
PHASE3_RESULTS_CSV = OUTPUT_ANALYSIS_DIR / "phase3_trade_results.csv"
SYNTHESIS_MD = OUTPUT_ANALYSIS_DIR / "SYNTHESIS.md"


# ===== Helpers (mirror trcb_filter/common.py) =====
def load_trade_log() -> pd.DataFrame:
    """Concatenate IS + OOS trade logs with sample tag, parse tz-aware."""
    is_df = pd.read_csv(IS_TRADE_LOG_PATH)
    is_df["sample"] = "IS"
    oos_df = pd.read_csv(OOS_TRADE_LOG_PATH)
    oos_df["sample"] = "OOS"
    if "hour_min" not in oos_df.columns:
        oos_df["hour_min"] = pd.NA

    df = pd.concat([is_df, oos_df], ignore_index=True)
    df["entry_time_utc"] = pd.to_datetime(df["entry_time"], utc=True)
    df["entry_time_et"] = df["entry_time_utc"].dt.tz_convert(TIMEZONE)
    df["exit_time_utc"] = pd.to_datetime(df["exit_time"], utc=True)
    df["exit_time_et"] = df["exit_time_utc"].dt.tz_convert(TIMEZONE)
    df = df.sort_values("entry_time_utc").reset_index(drop=True)
    # Cell tag for OMEN-minus-SL arm
    df["side_label"] = np.where(df["side"] == 1, "LONG", "SHORT")
    df["cell"] = df["side_label"] + "_" + df["gamma_regime"].astype(str)
    return df


def classify_trades(df: pd.DataFrame) -> pd.DataFrame:
    """Midpoint-rule trade classification (identical to v1)."""
    out = df.copy()
    bid = out["bid_px_00"].astype(float)
    ask = out["ask_px_00"].astype(float)
    px = out["price"].astype(float)
    out["midpoint"] = (bid + ask) / 2.0
    out["locked"] = (bid == ask)
    out["is_buy"] = (px >= out["midpoint"]) | out["locked"]
    out["is_sell"] = ~out["is_buy"]
    db_says_buy = (out["side"].astype(str) == "B")
    out["side_disagrees"] = (db_says_buy != out["is_buy"])
    return out


def rth_5min_bar_closes(session_date) -> pd.DatetimeIndex:
    """RTH 5-min bar closes for one ET session — 78 bars 09:35..16:00."""
    if isinstance(session_date, pd.Timestamp):
        d = session_date.date()
    else:
        d = session_date
    start = pd.Timestamp(d, tz=TIMEZONE) + pd.Timedelta("9h35m")
    end = pd.Timestamp(d, tz=TIMEZONE) + pd.Timedelta("16h0m")
    return pd.date_range(start, end, freq=BAR_FREQ, tz=TIMEZONE)


def wilder_atr(tr: pd.Series, n: int = ATR_WINDOW) -> pd.Series:
    return tr.ewm(alpha=1.0 / n, adjust=False, min_periods=n).mean()


def true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    pc = close.shift(1)
    return pd.concat([(high - low), (high - pc).abs(), (low - pc).abs()], axis=1).max(axis=1)
