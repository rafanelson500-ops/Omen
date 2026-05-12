"""Shared constants and helpers for the TRCB-v1 filter analysis.

Pre-registration commit b75e995 on branch diagnostics/mbp10-trcb-filter-v1.
Parameters locked per pre-reg Section 4.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

# ===== LOCKED PARAMETERS (per PREREG.md Section 4) =====
WINDOW_SECONDS = 60        # P1 detection window length (seconds post signal-bar-close)
VOLUME_MULT = 1.0          # P2 directional volume threshold (× trailing-100-bar median)
DELTA_RATIO = 2.0          # P3 directional:opposite aggressive volume ratio
PRICE_ATR_MULT = 0.25      # P4 net signed price move (× ATR_at_entry)
ATR_WINDOW = 14            # ATR lookback in 5-min bars
DIVISOR_FLOOR = 1          # V4.1 E34 convention — guard against 0-divisor in P3
TRAILING_MEDIAN_BARS = 100 # trailing-100-bar median for P2 baseline

RTH_START = "09:30"
RTH_END = "16:00"
TIMEZONE = "America/New_York"

BAR_FREQ = "5min"
BAR_FREQ_SECONDS = 300
FORWARD_RETURN_MINUTES = 25  # OMEN time-stop horizon for population-level signed return

# ===== Paths =====
REPO = Path("/Users/rafanelson/Omen")
MBP10_DIR = Path("/Users/rafanelson/Library/Caches/omen-pipeline-synthesis/mbp10_cache")
ES_1S_PATH = REPO / "backend/data/market/ES_c_0_ohlcv1s_2025-09-08_2026-04-27.parquet"

IS_TRADE_LOG_PATH = REPO / "backend/data/analysis/locked_baseline_trades_blackout_lunch.csv"
OOS_TRADE_LOG_PATH = REPO / "backend/data/analysis/oos_baseline_trades_2025-09-08_2025-12-23.csv"

OUTPUT_DIR = REPO / "diagnostics/mbp10-trcb-v1"
PER_BAR_VOLUMES_PATH = OUTPUT_DIR / "per_bar_volumes.parquet"
PHASE2_RESULTS_CSV = OUTPUT_DIR / "phase2_population_results.csv"
PHASE2_REPORT_MD = OUTPUT_DIR / "phase2_summary_report.md"

# Pre-reg commit hash for headers
PREREG_COMMIT = "b75e995"


# ===== Helpers =====
def load_trade_log() -> pd.DataFrame:
    """Concatenate IS + OOS trade logs with a 'sample' column ∈ {'IS','OOS'}.

    Returns a DataFrame with entry_time parsed as tz-aware UTC AND ET,
    sorted by entry_time. No deduplication (the two files are disjoint by date).
    """
    is_df = pd.read_csv(IS_TRADE_LOG_PATH)
    is_df["sample"] = "IS"
    oos_df = pd.read_csv(OOS_TRADE_LOG_PATH)
    oos_df["sample"] = "OOS"
    # OOS lacks `hour_min`; add NaN so concat schemas match.
    if "hour_min" not in oos_df.columns:
        oos_df["hour_min"] = pd.NA

    df = pd.concat([is_df, oos_df], ignore_index=True)
    # Parse entry_time with utc=True (handles mixed offsets across DST boundary),
    # then ET-localize a second copy for display / RTH operations.
    df["entry_time_utc"] = pd.to_datetime(df["entry_time"], utc=True)
    df["entry_time_et"] = df["entry_time_utc"].dt.tz_convert(TIMEZONE)
    df["exit_time_utc"] = pd.to_datetime(df["exit_time"], utc=True)
    df["exit_time_et"] = df["exit_time_utc"].dt.tz_convert(TIMEZONE)
    df = df.sort_values("entry_time_utc").reset_index(drop=True)
    return df


def classify_trades(df: pd.DataFrame) -> pd.DataFrame:
    """Apply the midpoint rule per pre-reg Section 3 to a trade-records subset.

    Input: df with columns price, bid_px_00, ask_px_00, side, size.
    The df should already be filtered to action == 'T'.

    Adds:
      midpoint: (bid + ask) / 2
      locked: bool, bid == ask
      is_buy: bool, classified as aggressive buy per midpoint rule + tie-breakers
      is_sell: bool, opposite
      side_disagrees: bool, midpoint rule disagrees with Databento side column
        (Databento side='B' on a trade = aggressive buy; side='A' = aggressive sell —
         verified empirically in Step 0)

    Tie-breakers per pre-reg Section 3:
      - price == midpoint → aggressive_buy (V4.1 E34 convention)
      - locked spread (bid == ask) → aggressive_buy
    """
    out = df.copy()
    bid = out["bid_px_00"].astype(float)
    ask = out["ask_px_00"].astype(float)
    px = out["price"].astype(float)
    out["midpoint"] = (bid + ask) / 2.0
    out["locked"] = (bid == ask)
    # is_buy includes the price >= mid case AND the locked case (which collapses)
    out["is_buy"] = (px >= out["midpoint"]) | out["locked"]
    out["is_sell"] = ~out["is_buy"]
    # Databento side convention (verified empirically Step 0):
    #   side='B' on trade row = aggressive buy
    #   side='A' on trade row = aggressive sell
    db_says_buy = (out["side"].astype(str) == "B")
    out["side_disagrees"] = (db_says_buy != out["is_buy"])
    return out


def rth_5min_bar_closes(session_date: pd.Timestamp) -> pd.DatetimeIndex:
    """RTH 5-min bar close timestamps for one session, tz-aware ET.

    For session_date d, bar closes at d 09:35:00, 09:40:00, ..., 16:00:00 ET.
    That is 78 bars per session (right-labeled, closed='right'; the bar at 09:35
    covers (09:30, 09:35]).
    """
    if isinstance(session_date, pd.Timestamp):
        d = session_date.date()
    else:
        d = session_date
    start = pd.Timestamp(d, tz=TIMEZONE) + pd.Timedelta("9h35m")
    end = pd.Timestamp(d, tz=TIMEZONE) + pd.Timedelta("16h0m")
    return pd.date_range(start, end, freq=BAR_FREQ, tz=TIMEZONE)


def wilder_atr(tr: pd.Series, n: int = ATR_WINDOW) -> pd.Series:
    """Wilder's RMA on TR. alpha = 1/n, no adjust.

    Pandas ewm(alpha=1/n, adjust=False) gives the recursive Wilder smoothing.
    A min_periods=n requirement enforces full-window warmup before the first
    finite ATR is emitted.
    """
    return tr.ewm(alpha=1.0 / n, adjust=False, min_periods=n).mean()


def true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    """Standard true range: max(H-L, |H-prev_close|, |L-prev_close|)."""
    pc = close.shift(1)
    return pd.concat([(high - low), (high - pc).abs(), (low - pc).abs()], axis=1).max(axis=1)
