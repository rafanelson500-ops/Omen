"""Step 0 — inventory of MBP-10 cache, ES 1s bars, GEX data, .env locations.

Identify all gaps between current on-disk coverage and today (May 12, 2026).
No data pulls in this step. Read-only.
"""
from __future__ import annotations

import os
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import pandas_market_calendars as mcal

# Paths
MBP10_CACHE = Path("/Users/rafanelson/Library/Caches/omen-pipeline-synthesis/mbp10_cache")
ES_DIR = Path("/Users/rafanelson/Omen/backend/data/market")
GEX_DIR = Path("/Users/rafanelson/Omen/backend/data/gex")
REPO = Path("/Users/rafanelson/Omen")
ENV_CANDIDATES = [
    REPO / ".env",
    REPO / "backend/.env",
    REPO / "backend/.env.local",
]

# Today's date (per user message: May 12 2026, RTH just closed)
TODAY = date(2026, 5, 12)
TZ = "America/New_York"

# NYSE calendar for trading day detection
NYSE = mcal.get_calendar("NYSE")


def nyse_trading_days(start: date, end: date) -> list[date]:
    """Inclusive list of NYSE trading days in [start, end]."""
    sched = NYSE.schedule(start_date=str(start), end_date=str(end))
    return [d.date() for d in sched.index]


# ---------- 1) MBP-10 cache ------------------------------------------------
def inventory_mbp10() -> dict:
    files = sorted(MBP10_CACHE.glob("front_month_*.parquet"))
    dates = []
    for p in files:
        try:
            d = date.fromisoformat(p.stem.replace("front_month_", ""))
            dates.append(d)
        except ValueError:
            continue
    dates_set = set(dates)
    first = min(dates) if dates else None
    last = max(dates) if dates else None
    expected = nyse_trading_days(first, TODAY) if first else []
    expected_set = set(expected)

    in_range_gaps = sorted(expected_set - dates_set)
    # Subdivide gaps into "interior" (before last cached) vs "missing-to-today"
    interior_gaps = [d for d in in_range_gaps if d <= last]
    forward_gaps = [d for d in in_range_gaps if d > last]

    return {
        "files": len(files),
        "dates": dates,
        "first": first,
        "last": last,
        "expected_trading_days": len(expected),
        "interior_gaps": interior_gaps,
        "forward_gaps": forward_gaps,
    }


# ---------- 2) ES 1s bars ---------------------------------------------------
def inventory_es_1s() -> dict:
    parquets = sorted(ES_DIR.glob("ES_c_0_ohlcv1s_*.parquet"))
    info = []
    for p in parquets:
        if p.is_symlink():
            info.append({"path": p.name, "is_symlink": True,
                         "target": os.readlink(p), "size": p.stat().st_size})
            continue
        size = p.stat().st_size
        info.append({"path": p.name, "is_symlink": False, "size": size})

    primary = ES_DIR / "ES_c_0_ohlcv1s_2025-09-08_2026-04-27.parquet"
    primary_loaded = None
    if primary.exists():
        df = pd.read_parquet(primary, columns=["close"])
        if not isinstance(df.index.dtype, pd.DatetimeTZDtype):
            df.index = pd.to_datetime(df.index, utc=True).tz_convert(TZ)
        primary_loaded = {
            "first_ts": df.index.min(),
            "last_ts": df.index.max(),
            "first_session": df.index.min().date(),
            "last_session": df.index.max().date(),
            "n_rows": len(df),
        }

    # Forward gap range: from last_session+1 trading day → today
    last_session = primary_loaded["last_session"] if primary_loaded else None
    forward_dates = []
    if last_session:
        td_range = nyse_trading_days(last_session, TODAY)
        forward_dates = [d for d in td_range if d > last_session]

    return {
        "files": info,
        "primary": primary_loaded,
        "forward_missing_dates": forward_dates,
    }


# ---------- 3) GEX coverage -------------------------------------------------
def inventory_gex() -> dict:
    parquets = sorted(GEX_DIR.glob("*.parquet"))
    missings = sorted(GEX_DIR.glob("*.missing"))
    dates = []
    for p in parquets:
        try:
            dates.append(date.fromisoformat(p.stem))
        except ValueError:
            continue
    miss_dates = []
    for p in missings:
        try:
            miss_dates.append(date.fromisoformat(p.stem))
        except ValueError:
            continue
    first = min(dates) if dates else None
    last = max(dates) if dates else None
    expected = nyse_trading_days(first, TODAY) if first else []
    expected_set = set(expected)
    dates_set = set(dates)
    interior_gaps = sorted([d for d in (expected_set - dates_set) if d <= last])
    forward_gaps = sorted([d for d in (expected_set - dates_set) if d > last])
    return {
        "parquet_files": len(parquets),
        "missing_sentinels": miss_dates,
        "first": first,
        "last": last,
        "expected_trading_days": len(expected),
        "interior_gaps": interior_gaps,
        "forward_gaps": forward_gaps,
    }


# ---------- 4) Databento API key ------------------------------------------
def inventory_env() -> dict:
    results = []
    for p in ENV_CANDIDATES:
        if not p.exists():
            results.append({"path": str(p), "exists": False, "has_databento_key": False,
                           "has_gexbot_key": False})
            continue
        text = p.read_text()
        results.append({
            "path": str(p),
            "exists": True,
            "has_databento_key": "DATABENTO_API_KEY" in text,
            "has_gexbot_key": "GEXBOT_API_KEY" in text,
            "size_bytes": p.stat().st_size,
        })
    return {"checked": results}


# ---------- Main report ----------------------------------------------------
def main() -> None:
    print("=" * 78)
    print(f"DATA INVENTORY — target: {TODAY.isoformat()}")
    print("=" * 78)

    # 1) MBP-10
    print("\n1) MBP-10 cache: /Users/rafanelson/Library/Caches/omen-pipeline-synthesis/mbp10_cache")
    mbp = inventory_mbp10()
    print(f"   files: {mbp['files']}")
    print(f"   first: {mbp['first']}    last: {mbp['last']}")
    print(f"   NYSE trading days in [first, today]: {mbp['expected_trading_days']}")
    print(f"   interior gaps (before last cached): {len(mbp['interior_gaps'])}")
    if mbp["interior_gaps"]:
        for d in mbp["interior_gaps"]:
            print(f"     • {d.isoformat()}")
    print(f"   forward gaps (after last cached, ≤ today): {len(mbp['forward_gaps'])}")
    for d in mbp["forward_gaps"]:
        print(f"     • {d.isoformat()}  ({d.strftime('%A')})")

    # 2) ES 1s
    print("\n2) ES 1s bars: backend/data/market/")
    es = inventory_es_1s()
    for f in es["files"]:
        if f.get("is_symlink"):
            print(f"   [SYMLINK] {f['path']}  →  {f['target']}")
        else:
            mb = f['size'] / (1024 * 1024)
            print(f"   [FILE   ] {f['path']}  {mb:.1f}MB")
    if es["primary"]:
        p = es["primary"]
        print(f"\n   Primary file (ES_c_0_ohlcv1s_2025-09-08_2026-04-27.parquet):")
        print(f"     rows:          {p['n_rows']:,}")
        print(f"     first_ts:      {p['first_ts']}")
        print(f"     last_ts:       {p['last_ts']}")
        print(f"     first_session: {p['first_session']}")
        print(f"     last_session:  {p['last_session']}")
    print(f"\n   Forward missing trading days (after last_session → today):")
    for d in es["forward_missing_dates"]:
        print(f"     • {d.isoformat()}  ({d.strftime('%A')})")
    if not es["forward_missing_dates"]:
        print("     (none)")

    # 3) GEX
    print("\n3) GEX data: backend/data/gex/")
    gex = inventory_gex()
    print(f"   parquet files:           {gex['parquet_files']}")
    print(f"   .missing sentinel files: {len(gex['missing_sentinels'])}")
    print(f"   first: {gex['first']}    last: {gex['last']}")
    print(f"   NYSE trading days in [first, today]: {gex['expected_trading_days']}")
    print(f"   interior gaps (before last cached):")
    if gex["interior_gaps"]:
        for d in gex["interior_gaps"]:
            sentinel = " (sentinel present)" if d in gex["missing_sentinels"] else ""
            print(f"     • {d.isoformat()}{sentinel}")
    else:
        print("     (none beyond .missing sentinels)")
    print(f"   forward gaps (after last cached, ≤ today):")
    for d in gex["forward_gaps"]:
        sentinel = " (sentinel present)" if d in gex["missing_sentinels"] else ""
        print(f"     • {d.isoformat()}  ({d.strftime('%A')}){sentinel}")
    if not gex["forward_gaps"]:
        print("     (none)")

    # 4) .env locations
    print("\n4) .env candidates")
    env = inventory_env()
    for r in env["checked"]:
        if not r["exists"]:
            print(f"   {r['path']:<40s}  [missing]")
            continue
        flags = []
        if r["has_databento_key"]:
            flags.append("DATABENTO_API_KEY ✓")
        if r["has_gexbot_key"]:
            flags.append("GEXBOT_API_KEY ✓")
        flag_str = ", ".join(flags) if flags else "(no relevant keys)"
        print(f"   {r['path']:<40s}  [present, {r['size_bytes']}B] {flag_str}")

    # 5) Gap summary
    print("\n" + "=" * 78)
    print("GAP SUMMARY")
    print("=" * 78)
    print(f"   MBP-10 missing:    {len(mbp['forward_gaps'])} forward gaps, "
          f"{len(mbp['interior_gaps'])} interior gaps")
    if mbp["forward_gaps"]:
        print(f"     forward: {[d.isoformat() for d in mbp['forward_gaps']]}")
    if mbp["interior_gaps"]:
        print(f"     interior: {[d.isoformat() for d in mbp['interior_gaps']]}")
    print(f"   ES 1s bars missing: {len(es['forward_missing_dates'])} forward sessions")
    if es["forward_missing_dates"]:
        fr = es["forward_missing_dates"]
        print(f"     range: {fr[0].isoformat()} → {fr[-1].isoformat()}  "
              f"({len(fr)} trading days)")
    print(f"   GEX missing:       {len(gex['forward_gaps'])} forward gaps, "
          f"{len(gex['interior_gaps'])} interior gaps (incl. sentinels)")
    if gex["forward_gaps"]:
        print(f"     forward: {[d.isoformat() for d in gex['forward_gaps']]}")


if __name__ == "__main__":
    main()
