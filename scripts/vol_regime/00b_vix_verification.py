"""Step 0.5 — verify VIX data before any analysis uses it.

Read-only. Decision deferred to user. STOP after producing this report.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

DISCLOSURE = """\
This analysis is exploratory diagnostic work on a consumed corpus
during an active forward test. It is NOT pre-registered. Results
CANNOT authorize any modification to locked OMEN config or pre-reg.

The OMEN trade outcomes on this 146-session corpus have been examined
many times across TRCB-v1, TRCB-v2 Q1-Q9 post-mortems, microprice
continuation, cell exclusion analysis, churn analysis (Steps 5/7),
and other diagnostics. The corpus is heavily consumed and the
project-wide false discovery rate is high.

Any positive finding here can only be honestly evaluated on a future
pre-registered forward window. This diagnostic adds candidate
filters to the post-verdict pre-reg bookmarks, nothing more.
"""

REPO = Path("/Users/rafanelson/Omen")
VIX_DAILY_PATH = REPO / "backend/data/analysis/vix_daily.csv"
TRADES_WITH_VIX_PATH = REPO / "backend/data/analysis/trades_with_vix.csv"
IS_BUGFIX = REPO / "diagnostics/all-bugfixes-baseline/is_all_bugfixes.csv"
OOS_BUGFIX = REPO / "diagnostics/all-bugfixes-baseline/oos_all_bugfixes.csv"

OUT_DIR = REPO / "diagnostics/vol-regime"
OUT_MD = OUT_DIR / "00b_vix_verification.md"


def _load_bugfixed_trades() -> pd.DataFrame:
    is_df = pd.read_csv(IS_BUGFIX); is_df["sample"] = "IS"
    oos_df = pd.read_csv(OOS_BUGFIX); oos_df["sample"] = "OOS"
    df = pd.concat([is_df, oos_df], ignore_index=True)
    df["entry_time_utc"] = pd.to_datetime(df["entry_time"], utc=True)
    df["entry_date"] = df["entry_time_utc"].dt.tz_convert("America/New_York").dt.date
    return df


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(DISCLOSURE)
    print("=" * 78)
    print("STEP 0.5 — VIX data verification")
    print("=" * 78)
    print()

    trades = _load_bugfixed_trades()
    trade_sessions = sorted(trades["entry_date"].unique())
    n_trades = len(trades); n_sessions = len(trade_sessions)
    print(f"Reference: bugfixed all-trades log = {n_trades} trades, "
          f"{n_sessions} sessions")
    print(f"  range: {trade_sessions[0]} → {trade_sessions[-1]}\n")

    # ---- 1. vix_daily.csv ----
    print("1) vix_daily.csv")
    daily = pd.read_csv(VIX_DAILY_PATH)
    print(f"   path : {VIX_DAILY_PATH}")
    print(f"   rows : {len(daily)}")
    print(f"   cols : {list(daily.columns)}")
    print(f"   dtypes:")
    for c, t in daily.dtypes.items():
        print(f"     {c:<20s}  {t}")
    print(f"   first 5 rows:")
    print(daily.head().to_string(index=False))
    print()

    # Find the date column heuristically
    date_col = None
    for cand in ("date", "Date", "session_date", "trade_date", "DATE"):
        if cand in daily.columns:
            date_col = cand
            break
    if date_col is None:
        for c in daily.columns:
            try:
                pd.to_datetime(daily[c].iloc[:5])
                date_col = c
                break
            except Exception:
                continue
    print(f"   inferred date column: {date_col}")

    daily_coverage = None
    daily_missing_for_trades = None
    if date_col is not None:
        daily["_date"] = pd.to_datetime(daily[date_col]).dt.date
        daily_dates = set(daily["_date"].unique())
        coverage = sum(1 for d in trade_sessions if d in daily_dates)
        missing = [d for d in trade_sessions if d not in daily_dates]
        print(f"   trade-sessions covered by vix_daily: {coverage} / {n_sessions}")
        print(f"   range covered: {min(daily['_date'])} → {max(daily['_date'])}")
        print(f"   missing trade-sessions: {len(missing)}")
        if missing[:10]:
            print(f"     first 10: {[str(d) for d in missing[:10]]}")
        daily_coverage = coverage
        daily_missing_for_trades = missing
    print()

    # ---- 2. trades_with_vix.csv ----
    print("2) trades_with_vix.csv")
    twv = pd.read_csv(TRADES_WITH_VIX_PATH)
    print(f"   path : {TRADES_WITH_VIX_PATH}")
    print(f"   rows : {len(twv)}")
    print(f"   cols : {list(twv.columns)}")
    print(f"   first 5 rows:")
    print(twv.head().to_string(index=False))
    print()

    # Check trade match against all-bugfixes log on (entry_time, side)
    # Build join keys
    def _key(df, t_col, side_col):
        ts = pd.to_datetime(df[t_col], utc=True, errors="coerce")
        if ts.isna().all():
            ts = pd.to_datetime(df[t_col], errors="coerce")
        return list(zip(ts.dt.tz_convert(None) if ts.dt.tz is not None else ts,
                          df[side_col]))

    # Try to find entry_time and side columns in trades_with_vix
    twv_t_col = next((c for c in ("entry_time", "entry_time_utc", "entry_ts",
                                    "entry_timestamp") if c in twv.columns), None)
    twv_s_col = next((c for c in ("side", "Side", "direction") if c in twv.columns),
                      None)
    print(f"   inferred entry_time column: {twv_t_col}")
    print(f"   inferred side column      : {twv_s_col}")

    match_count = None
    twv_n = len(twv)
    if twv_t_col and twv_s_col:
        ref_keys = set(_key(trades, "entry_time", "side"))
        twv_keys = set(_key(twv, twv_t_col, twv_s_col))
        match_count = len(twv_keys & ref_keys)
        only_in_twv = len(twv_keys - ref_keys)
        only_in_ref = len(ref_keys - twv_keys)
        print(f"   exact (entry_time, side) match count: {match_count} / {twv_n}")
        print(f"   keys only in trades_with_vix : {only_in_twv}")
        print(f"   keys only in all-bugfixes ref: {only_in_ref}")
    else:
        print("   [WARN] could not locate matching columns for key-join check.")

    # Determine if twv looks "clean and complete"
    is_full_504 = (twv_n == 504 and match_count == 504)
    is_filtered = (twv_n != 504) or (match_count != 504)
    print()
    print(f"   verdict: "
          f"{'CLEAN & COMPLETE (full 504-trade match)' if is_full_504 else 'FILTERED or partial — DO NOT use as shortcut'}")

    # ---- Markdown ----
    L: list[str] = []
    L.append("# Step 0.5 — VIX data verification\n")
    L.append("Branch: `analysis/vol-regime-conditioning-throwaway` "
             "(throwaway / never merges).")
    L.append(f"Generated: {datetime.now().isoformat(timespec='seconds')}\n")
    L.append("## Disclosure\n")
    L.append("```")
    L.append(DISCLOSURE)
    L.append("```\n")

    L.append("## Reference\n")
    L.append(f"- All-bugfixes IS+OOS trade log: **{n_trades} trades, "
             f"{n_sessions} sessions** ({trade_sessions[0]} → {trade_sessions[-1]}).")
    L.append("")

    L.append("## 1. vix_daily.csv\n")
    L.append(f"- path: `{VIX_DAILY_PATH}`")
    L.append(f"- rows: {len(daily)}")
    L.append(f"- columns: `{list(daily.columns)}`")
    L.append("")
    L.append("Dtypes:")
    L.append("")
    L.append("```")
    for c, t in daily.dtypes.items():
        L.append(f"  {c:<20s}  {t}")
    L.append("```")
    L.append("")
    L.append("First 5 rows:")
    L.append("")
    L.append("```")
    L.append(daily.head().to_string(index=False))
    L.append("```")
    L.append("")
    if date_col is not None:
        L.append(f"Inferred date column: **`{date_col}`**.")
        L.append(f"- VIX coverage of trade-sessions: "
                 f"**{daily_coverage} / {n_sessions}**")
        L.append(f"- VIX file range: "
                 f"**{min(daily['_date'])} → {max(daily['_date'])}**")
        L.append(f"- Trade-sessions missing from vix_daily: "
                 f"**{len(daily_missing_for_trades) if daily_missing_for_trades else 0}**")
        if daily_missing_for_trades:
            L.append(f"  - first 10: {[str(d) for d in daily_missing_for_trades[:10]]}")
        L.append("")

    L.append("## 2. trades_with_vix.csv\n")
    L.append(f"- path: `{TRADES_WITH_VIX_PATH}`")
    L.append(f"- rows: {twv_n}")
    L.append(f"- columns: `{list(twv.columns)}`")
    L.append("")
    L.append("First 5 rows:")
    L.append("")
    L.append("```")
    L.append(twv.head().to_string(index=False))
    L.append("```")
    L.append("")
    L.append(f"Inferred join columns: `entry_time` = `{twv_t_col}`, "
             f"`side` = `{twv_s_col}`.")
    if match_count is not None:
        L.append("")
        L.append(f"**Key-match against all-bugfixes ref (entry_time, side)**:")
        L.append(f"- matches    : {match_count}")
        L.append(f"- only in TWV: {len(set(_key(twv, twv_t_col, twv_s_col)) - set(_key(trades, 'entry_time', 'side')))}")
        L.append(f"- only in ref: {len(set(_key(trades, 'entry_time', 'side')) - set(_key(twv, twv_t_col, twv_s_col)))}")
    L.append("")

    # Verdict
    L.append("## 3. Verdict\n")
    if is_full_504:
        L.append("**`trades_with_vix.csv` IS clean and complete** — every one of the "
                 "504 all-bugfixes trades has an exact (entry_time, side) match. "
                 "Safe to use directly in Step 2.")
    else:
        L.append(f"**`trades_with_vix.csv` is FILTERED or partial** "
                 f"({twv_n} rows; "
                 f"{match_count if match_count is not None else 'unknown'} match the "
                 f"504-trade reference). **Per spec, DO NOT use it as a shortcut.** "
                 "Step 2 will perform a fresh join from `vix_daily.csv` to the full "
                 "504-trade log on session date.")
    L.append("")
    L.append("## 4. Stop gate\n")
    L.append("Per spec, **STOP HERE**. Step 1 (ATR) runs only after you confirm "
             "this verification.")
    L.append("")

    OUT_MD.write_text("\n".join(L) + "\n")
    print()
    print(f"Saved: {OUT_MD}")
    print()
    print("=" * 78)
    print("STOPPED per spec — Step 1+ awaits your confirmation.")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
