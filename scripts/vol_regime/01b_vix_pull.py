"""Step 1.5 — pull VIX daily history from CBOE public CSV.

Free, no auth, no Databento. Saves to backend/data/analysis/vix_daily_full.csv.
Does NOT touch backend/data/analysis/vix_daily.csv.
"""
from __future__ import annotations

import sys
from io import StringIO
from pathlib import Path

import pandas as pd
import requests

REPO = Path("/Users/rafanelson/Omen")
IS_BUGFIX = REPO / "diagnostics/all-bugfixes-baseline/is_all_bugfixes.csv"
OOS_BUGFIX = REPO / "diagnostics/all-bugfixes-baseline/oos_all_bugfixes.csv"
OUT_CSV = REPO / "backend/data/analysis/vix_daily_full.csv"
URL = "https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv"

START = pd.Timestamp("2025-09-08").date()
END = pd.Timestamp("2026-05-13").date()
MAX_ALLOWED_GAP = 5


def main() -> int:
    print("Pulling CBOE VIX_History.csv ...")
    try:
        resp = requests.get(URL, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        print(f"[FATAL] download failed: {type(e).__name__}: {e}")
        return 1
    raw = pd.read_csv(StringIO(resp.text))
    print(f"  rows raw: {len(raw)}")
    print(f"  columns : {list(raw.columns)}")
    print(f"  first 5 rows:")
    print(raw.head().to_string(index=False))

    # Find DATE and CLOSE columns case-insensitively
    cols_lower = {c.lower(): c for c in raw.columns}
    if "date" not in cols_lower:
        print("[FATAL] no DATE column"); return 1
    if "close" not in cols_lower:
        print(f"[FATAL] no CLOSE column. Available: {list(raw.columns)}"); return 1
    date_col = cols_lower["date"]
    close_col = cols_lower["close"]

    raw["_date"] = pd.to_datetime(raw[date_col], errors="coerce").dt.date
    n_unparseable = int(raw["_date"].isna().sum())
    if n_unparseable:
        print(f"  [WARN] {n_unparseable} unparseable date rows dropped")
    raw = raw.dropna(subset=["_date"]).copy()

    # Filter date range
    in_range = raw[(raw["_date"] >= START) & (raw["_date"] <= END)].copy()
    out = in_range[["_date", close_col]].rename(
        columns={"_date": "date", close_col: "vix_close"}
    ).sort_values("date").reset_index(drop=True)
    print(f"\nFiltered to {START} → {END}: {len(out)} rows")
    if not out.empty:
        print(f"  range covered: {out['date'].min()} → {out['date'].max()}")

    # Coverage check vs trade sessions
    is_df = pd.read_csv(IS_BUGFIX); oos_df = pd.read_csv(OOS_BUGFIX)
    trades = pd.concat([is_df, oos_df], ignore_index=True)
    trades["_date"] = pd.to_datetime(trades["entry_time"],
                                       utc=True).dt.tz_convert(
        "America/New_York").dt.date
    trade_sessions = set(trades["_date"].unique())
    vix_dates = set(out["date"].tolist())
    missing = sorted(d for d in trade_sessions if d not in vix_dates)
    print(f"\nCoverage vs 146 trade-sessions:")
    print(f"  covered : {len(trade_sessions) - len(missing)} / {len(trade_sessions)}")
    print(f"  gaps    : {len(missing)}")
    if missing:
        for d in missing[:10]:
            print(f"    {d}")
        if len(missing) > 10:
            print(f"    ... and {len(missing) - 10} more")

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT_CSV, index=False)
    print(f"\nSaved: {OUT_CSV}  ({len(out)} rows)")

    if len(missing) > MAX_ALLOWED_GAP:
        print(f"\n[STOP] coverage gap {len(missing)} > {MAX_ALLOWED_GAP} sessions. "
              "Investigate before proceeding to Step 2.")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
