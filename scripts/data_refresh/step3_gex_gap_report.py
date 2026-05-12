"""Step 3 — GEX gap identification ONLY (no API calls, no pull).

Surfaces the missing dates and documents the exact pull-mechanism command
(backend/scripts/fetch_gex.py) for the user to run separately. GexBot
historical-API access is unrelated to the Databento credit pool, so we
keep the two systems decoupled per the user's protocol.

This script is read-only: no network calls.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import pandas_market_calendars as mcal

GEX_DIR = Path("/Users/rafanelson/Omen/backend/data/gex")
TODAY = dt.date(2026, 5, 12)
NYSE = mcal.get_calendar("NYSE")

# Known unrecoverable dates (confirmed prior pulls)
KNOWN_UNRECOVERABLE: set[dt.date] = {
    dt.date(2026, 2, 23),   # source-of-record missing for GexBot + MBP-10
}


def _trading_days(start: dt.date, end: dt.date) -> list[dt.date]:
    sched = NYSE.schedule(start_date=str(start), end_date=str(end))
    return [d.date() for d in sched.index]


def _inventory_gex() -> dict:
    parquets = sorted(GEX_DIR.glob("*.parquet"))
    missings = sorted(GEX_DIR.glob("*.missing"))
    dates: list[dt.date] = []
    for p in parquets:
        try:
            dates.append(dt.date.fromisoformat(p.stem))
        except ValueError:
            continue
    sentinels: list[dt.date] = []
    for p in missings:
        try:
            sentinels.append(dt.date.fromisoformat(p.stem))
        except ValueError:
            continue
    if not dates:
        return {"first": None, "last": None, "dates": [], "sentinels": sentinels,
                "interior_gaps": [], "forward_gaps": []}
    first, last = min(dates), max(dates)
    expected = _trading_days(first, TODAY)
    have = set(dates)
    miss = sorted(set(expected) - have)
    interior = [d for d in miss if d <= last]
    forward = [d for d in miss if d > last]
    return {
        "first": first, "last": last,
        "dates": dates, "sentinels": sentinels,
        "interior_gaps": interior, "forward_gaps": forward,
    }


def main() -> int:
    print("=" * 78)
    print("STEP 3 — GEX gap report (no pull)")
    print("=" * 78)
    inv = _inventory_gex()
    print(f"gex_dir:  {GEX_DIR}")
    print(f"first:    {inv['first']}")
    print(f"last:     {inv['last']}")
    print(f"parquet:  {len(inv['dates'])}")
    print(f"sentinels: {len(inv['sentinels'])}")
    for d in inv["sentinels"]:
        flag = " (KNOWN UNRECOVERABLE)" if d in KNOWN_UNRECOVERABLE else ""
        print(f"            {d.isoformat()}{flag}")

    actionable_interior = [d for d in inv["interior_gaps"]
                            if d not in KNOWN_UNRECOVERABLE
                            and d not in inv["sentinels"]]
    print(f"\nInterior gaps (between first and last cached):")
    for d in inv["interior_gaps"]:
        flag = ""
        if d in KNOWN_UNRECOVERABLE:
            flag = " (KNOWN UNRECOVERABLE — do not retry)"
        elif d in inv["sentinels"]:
            flag = " (.missing sentinel present)"
        print(f"  {d.isoformat()}{flag}")
    print(f"  actionable: {len(actionable_interior)}")

    print(f"\nForward gaps (after last cached, up to {TODAY.isoformat()}):")
    for d in inv["forward_gaps"]:
        weekday = d.strftime("%A")
        print(f"  {d.isoformat()}  ({weekday})")
    print(f"  total: {len(inv['forward_gaps'])}")

    print("\n" + "-" * 78)
    print("PULL MECHANISM (run separately when ready — NOT invoked here)")
    print("-" * 78)
    print("Backend script  : backend/scripts/fetch_gex.py")
    print("API key var     : GEXBOT_API_KEY (already present in backend/.env)")
    print("Endpoint pattern: GET https://api.gex.bot/v2/hist/ES_SPX/orderflow/")
    print("                  orderflow/{YYYY-M-D}?noredirect")
    print()
    if inv["forward_gaps"]:
        start = inv["forward_gaps"][0].isoformat()
        end = inv["forward_gaps"][-1].isoformat()
        print(f"Suggested command (do NOT auto-run):")
        print(f"  cd /Users/rafanelson/Omen")
        print(f"  python backend/scripts/fetch_gex.py --start {start} --end {end}")
    else:
        print("No forward gaps; no GEX pull needed.")
    print()
    print("Notes:")
    print(f"  - {TODAY.isoformat()} (today) may still be unavailable")
    print("    via the historical orderflow endpoint until end-of-day rollover.")
    print("  - 2026-04-29 has a .missing sentinel from the prior bulk pull")
    print("    (that pull's run-day couldn't fetch its own end-day data).")
    print("    A re-run today should now succeed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
