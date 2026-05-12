"""Step 4 — verify post-pull state.

Re-runs the inventory diff (MBP-10 cache + ES 1s bars + GEX) and additionally:
  - sample-loads each newly written MBP-10 parquet, confirms schema parity
    + non-zero trade rows + index timezone
  - loads the new ES 1s parquet, confirms ATR-relevant invariants
    (close has no NaN, monotonic index, expected session-date set)
  - reports the final forward-gap state per source

Read-only on data; writes only to stdout.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import pandas_market_calendars as mcal

# Paths
MBP10_CACHE = Path("/Users/rafanelson/Library/Caches/omen-pipeline-synthesis/mbp10_cache")
ES_DIR = Path("/Users/rafanelson/Omen/backend/data/market")
GEX_DIR = Path("/Users/rafanelson/Omen/backend/data/gex")

TODAY = dt.date(2026, 5, 12)
ET = ZoneInfo("America/New_York")
NYSE = mcal.get_calendar("NYSE")

NEW_MBP10_DATES = [
    dt.date(2026, 4, 29), dt.date(2026, 4, 30), dt.date(2026, 5, 1),
    dt.date(2026, 5, 4),  dt.date(2026, 5, 5),  dt.date(2026, 5, 6),
    dt.date(2026, 5, 7),  dt.date(2026, 5, 8),  dt.date(2026, 5, 11),
]
NEW_ES_FILE = ES_DIR / "ES_c_0_ohlcv1s_2026-04-28_2026-05-11.parquet"
REF_MBP10 = MBP10_CACHE / "front_month_2026-04-28.parquet"


def _section(t: str) -> None:
    print("\n" + "=" * 78)
    print(t)
    print("=" * 78)


def _trading_days(s: dt.date, e: dt.date) -> list[dt.date]:
    sched = NYSE.schedule(start_date=str(s), end_date=str(e))
    return [d.date() for d in sched.index]


# ── 1) MBP-10 verification ────────────────────────────────────────────────────
def _verify_mbp10() -> None:
    _section("1) MBP-10 verification")
    ref = pd.read_parquet(REF_MBP10)
    ref_cols = list(ref.columns)
    ref_dtypes = {c: str(ref[c].dtype) for c in ref_cols}
    print(f"reference: {REF_MBP10.name}  cols={len(ref_cols)}  index='{ref.index.name}'")
    del ref

    fail = False
    for d in NEW_MBP10_DATES:
        p = MBP10_CACHE / f"front_month_{d.isoformat()}.parquet"
        m = MBP10_CACHE / f"front_month_{d.isoformat()}.meta.json"
        if not p.exists() or not m.exists():
            print(f"  [{d}] MISSING parquet or meta — FAIL")
            fail = True
            continue
        df = pd.read_parquet(p)
        meta = json.loads(m.read_text())

        cols = list(df.columns)
        cols_ok = cols == ref_cols
        dtypes_ok = all(str(df[c].dtype) == ref_dtypes[c] for c in ref_cols)
        idx_ok = (df.index.name == "ts_recv"
                  and isinstance(df.index, pd.DatetimeIndex)
                  and str(df.index.tz) == "UTC")
        nrows = len(df)
        n_trades = int((df["action"] == "T").sum()) if "action" in df.columns else -1
        iid_ok = df["instrument_id"].nunique() == 1
        sym = str(df["symbol"].iloc[0]) if "symbol" in df.columns else "?"

        # Check RTH window
        first, last = df.index.min(), df.index.max()
        rth_open_utc = pd.Timestamp(dt.datetime(d.year, d.month, d.day, 9, 30, tzinfo=ET)).tz_convert("UTC")
        rth_close_utc = pd.Timestamp(dt.datetime(d.year, d.month, d.day, 16, 0, tzinfo=ET)).tz_convert("UTC")
        rth_ok = first >= rth_open_utc and last < rth_close_utc

        verdict = "OK" if (cols_ok and dtypes_ok and idx_ok and iid_ok and rth_ok
                            and n_trades > 0) else "FAIL"
        if verdict == "FAIL":
            fail = True
        size_mb = p.stat().st_size / (1024 * 1024)
        print(f"  [{d}] {verdict:4s}  rows={nrows:>10,}  trades={n_trades:>7,}  "
              f"size={size_mb:6.1f}MB  iid={meta['front_month']['instrument_id']}  "
              f"sym='{sym}'")
        if not cols_ok:
            print(f"    cols differ")
        if not dtypes_ok:
            print(f"    dtypes differ")
        if not idx_ok:
            print(f"    index not ts_recv/UTC")
        if not iid_ok:
            print(f"    multiple instrument_ids")
        if not rth_ok:
            print(f"    out-of-RTH bars: first={first}  last={last}")

    print(f"\n  verdict: {'ALL PASS' if not fail else 'AT LEAST ONE FAIL'}")


# ── 2) ES 1s verification ────────────────────────────────────────────────────
def _verify_es_1s() -> None:
    _section("2) ES 1s bars verification")
    if not NEW_ES_FILE.exists():
        print(f"  MISSING: {NEW_ES_FILE}")
        return
    df = pd.read_parquet(NEW_ES_FILE)
    print(f"  file:  {NEW_ES_FILE.name}")
    print(f"  rows:  {len(df):,}")
    print(f"  cols:  {list(df.columns)}")
    print(f"  index: name={df.index.name!r}  tz={df.index.tz}")
    print(f"  first: {df.index.min()}")
    print(f"  last : {df.index.max()}")

    # Invariants
    monotonic = df.index.is_monotonic_increasing
    no_nan_close = df["close"].isna().sum() == 0
    pos_volume = (df["volume"] >= 0).all()
    print(f"\n  monotonic index : {monotonic}")
    print(f"  no NaN in close : {no_nan_close}")
    print(f"  volume >= 0     : {pos_volume}")

    # Session-date coverage
    session_dates = sorted(set(df.index.date))
    print(f"\n  unique session-dates: {len(session_dates)}")
    for d in session_dates:
        n = (df.index.date == d).sum()
        print(f"    {d.isoformat()}  bars={n:,}")

    # NYSE trading-day check for Apr 28 -> May 11
    expected_trading = set(_trading_days(dt.date(2026, 4, 28), dt.date(2026, 5, 11)))
    present_trading = set(session_dates) & expected_trading
    missing_trading = sorted(expected_trading - present_trading)
    print(f"\n  expected NYSE trading days in [4/28, 5/11]: {len(expected_trading)}")
    print(f"  trading days present:                       {len(present_trading)}")
    if missing_trading:
        print(f"  MISSING trading days: {[d.isoformat() for d in missing_trading]}")
    else:
        print(f"  no missing trading days")


# ── 3) Combined gap status ────────────────────────────────────────────────────
def _final_gap_status() -> None:
    _section("3) Final forward-gap status (per source)")
    # MBP-10
    mbp = sorted(d.fromisoformat(p.stem.replace("front_month_", ""))
                 for p in MBP10_CACHE.glob("front_month_*.parquet")
                 if (d := dt.date).fromisoformat)  # noqa: E731
    mbp = [dt.date.fromisoformat(p.stem.replace("front_month_", ""))
            for p in sorted(MBP10_CACHE.glob("front_month_*.parquet"))]
    mbp_set = set(mbp)
    mbp_first, mbp_last = min(mbp), max(mbp)
    mbp_expected = set(_trading_days(mbp_first, TODAY))
    mbp_miss = sorted(mbp_expected - mbp_set)
    print(f"  MBP-10: {len(mbp)} files  range {mbp_first} .. {mbp_last}")
    print(f"    forward gaps: {[d.isoformat() for d in mbp_miss if d > mbp_last]}")
    interior_unknown = [d for d in mbp_miss
                         if d <= mbp_last and d != dt.date(2026, 2, 23)]
    print(f"    interior gaps (excl. known unrecoverable Feb-23): {[d.isoformat() for d in interior_unknown]}")

    # ES 1s
    primary = ES_DIR / "ES_c_0_ohlcv1s_2025-09-08_2026-04-27.parquet"
    new = NEW_ES_FILE
    parts = []
    for f in (primary, new):
        if f.exists():
            df = pd.read_parquet(f, columns=["close"])
            df.index = pd.to_datetime(df.index, utc=True).tz_convert(ET)
            parts.append((f, df.index.min(), df.index.max()))
    print(f"\n  ES 1s parts:")
    for f, a, b in parts:
        print(f"    {f.name}: {a} .. {b}")
    if parts:
        combined_last = max(b for _, _, b in parts).date()
        # Compute forward gaps after combined last-session
        full = _trading_days(parts[0][1].date(), TODAY)
        covered = {b.date() for _, _, b in parts} | set()
        # actual coverage = union of dates in each file
        coverage_dates = set()
        for f, a, b in parts:
            df = pd.read_parquet(f, columns=["close"])
            df.index = pd.to_datetime(df.index, utc=True).tz_convert(ET)
            coverage_dates |= set(df.index.date)
        missing_trading = [d for d in full if d not in coverage_dates]
        print(f"    combined trading-day coverage: {len(set(full) & coverage_dates)} / {len(full)}")
        print(f"    forward trading-day gaps: {[d.isoformat() for d in missing_trading if d > combined_last]}")

    # GEX (no change in this step — same as Step 3 report)
    gex_files = sorted(GEX_DIR.glob("*.parquet"))
    gex_dates = sorted(dt.date.fromisoformat(p.stem) for p in gex_files
                       if len(p.stem) == 10)
    gex_set = set(gex_dates)
    gex_first, gex_last = min(gex_dates), max(gex_dates)
    gex_expected = set(_trading_days(gex_first, TODAY))
    gex_miss = sorted(gex_expected - gex_set)
    print(f"\n  GEX: {len(gex_dates)} files  range {gex_first} .. {gex_last}")
    print(f"    forward gaps: {[d.isoformat() for d in gex_miss if d > gex_last]}")
    print(f"    interior gaps (excl. known unrecoverable Feb-23): "
          f"{[d.isoformat() for d in gex_miss if d <= gex_last and d != dt.date(2026, 2, 23)]}")


def main() -> int:
    _verify_mbp10()
    _verify_es_1s()
    _final_gap_status()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
