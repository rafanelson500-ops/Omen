"""
gexbot_archive_pull.py

Bulk-download GexBot's historical SPX orderflow archive while we have access.

Pulls every weekday from --start to --end, saves raw JSON to disk.
Resumable: skips files already on disk. Safe to Ctrl+C and re-run.

Usage:
    python3 gexbot_archive_pull.py
    python3 gexbot_archive_pull.py --start 2025-10-01 --end 2026-04-27
    python3 gexbot_archive_pull.py --ticker SPY
"""
from __future__ import annotations

import argparse
import os
import sys
import time
import urllib.request
import urllib.error
import json
from datetime import date, timedelta
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────
AUTH_COOKIE = "vHj8ra5jHnRnCwVEukNZRbr6n8in8jUD"
ARCHIVE_DIR = Path("./backend/data/gex_archive_raw")
RATE_LIMIT_SEC = 3.0   # seconds between successful requests (be polite)
NODATA_SLEEP = 0.5     # short sleep when no data for a date
TIMEOUT_SEC = 60
URL_RESOLVE = "https://app.gexbot.com/hist/{ticker}/orderflow/orderflow/{date}?noredirect"

HEADERS = {
    "Origin": "https://www.gexbot.com",
    "Accept": "application/json",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36"
    ),
    "Cookie": f"auth={AUTH_COOKIE}",
}


# ── HTTP helpers (stdlib only — no pip install needed) ────────────────────────
def http_get(url: str, headers: dict, timeout: int = TIMEOUT_SEC) -> tuple[int, bytes]:
    """GET request. Returns (status_code, body). Doesn't raise on HTTP errors."""
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def download_to_file(url: str, dest: Path, timeout: int = TIMEOUT_SEC * 2) -> int:
    """Download URL to dest. Returns bytes written."""
    req = urllib.request.Request(url)
    bytes_written = 0
    with urllib.request.urlopen(req, timeout=timeout) as resp, open(dest, "wb") as f:
        while True:
            chunk = resp.read(65536)
            if not chunk:
                break
            f.write(chunk)
            bytes_written += len(chunk)
    return bytes_written


# ── Date iteration ────────────────────────────────────────────────────────────
def weekdays_between(start: date, end: date):
    cur = start
    while cur <= end:
        if cur.weekday() < 5:  # 0=Mon, 4=Fri
            yield cur
        cur += timedelta(days=1)


def fmt_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:6.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


# ── Main ──────────────────────────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default="2025-10-01", help="Start date YYYY-MM-DD")
    parser.add_argument("--end",   default=date.today().isoformat(), help="End date YYYY-MM-DD")
    parser.add_argument("--ticker", default="SPX", help="Ticker symbol (SPX, SPY, ES, etc.)")
    parser.add_argument("--rate-limit", type=float, default=RATE_LIMIT_SEC,
                        help="Seconds between requests (default: 3.0)")
    args = parser.parse_args()

    start = date.fromisoformat(args.start)
    end   = date.fromisoformat(args.end)
    ticker = args.ticker.upper()
    rate_limit = args.rate_limit

    archive_dir = ARCHIVE_DIR / ticker
    archive_dir.mkdir(parents=True, exist_ok=True)

    dates = list(weekdays_between(start, end))
    print("=" * 70)
    print(f"GexBot archive bulk-download")
    print("=" * 70)
    print(f"  Ticker:      {ticker}")
    print(f"  Range:       {start} to {end}")
    print(f"  Weekdays:    {len(dates)}")
    print(f"  Archive dir: {archive_dir.absolute()}")
    print(f"  Rate limit:  {rate_limit}s between requests")
    print(f"  Estimated:   ~{len(dates) * rate_limit / 60:.1f} min total")
    print("=" * 70)
    print()

    stats = {"downloaded": 0, "skipped": 0, "no_data": 0, "errors": 0, "bytes": 0}
    t_start = time.monotonic()

    try:
        for i, d in enumerate(dates, 1):
            filename = f"{d.isoformat()}_{ticker}_orderflow.json"
            dest = archive_dir / filename

            # Skip if already downloaded
            if dest.exists() and dest.stat().st_size > 1000:
                size = dest.stat().st_size
                stats["skipped"] += 1
                print(f"[{i:>3}/{len(dates)}] {d}  SKIP    ({fmt_size(size)} on disk)")
                continue

            # Step 1: get SAS URL
            resolve_url = URL_RESOLVE.format(ticker=ticker, date=d.isoformat())
            try:
                code, body = http_get(resolve_url, HEADERS)
            except Exception as e:
                stats["errors"] += 1
                print(f"[{i:>3}/{len(dates)}] {d}  ERROR   resolve: {e}")
                time.sleep(rate_limit)
                continue

            if code == 404:
                stats["no_data"] += 1
                print(f"[{i:>3}/{len(dates)}] {d}  NO DATA (holiday/before archive)")
                time.sleep(NODATA_SLEEP)
                continue

            if code != 200:
                stats["errors"] += 1
                print(f"[{i:>3}/{len(dates)}] {d}  ERROR   resolve HTTP {code}")
                time.sleep(rate_limit)
                continue

            try:
                payload = json.loads(body)
                blob_url = payload.get("url")
                if not blob_url:
                    stats["errors"] += 1
                    print(f"[{i:>3}/{len(dates)}] {d}  ERROR   no URL in response")
                    time.sleep(rate_limit)
                    continue
            except json.JSONDecodeError:
                stats["errors"] += 1
                print(f"[{i:>3}/{len(dates)}] {d}  ERROR   bad JSON in resolve")
                time.sleep(rate_limit)
                continue

            # Step 2: download from Azure
            try:
                bytes_written = download_to_file(blob_url, dest)
                stats["downloaded"] += 1
                stats["bytes"] += bytes_written
                elapsed = time.monotonic() - t_start
                print(f"[{i:>3}/{len(dates)}] {d}  OK      {fmt_size(bytes_written)}  "
                      f"(total: {fmt_size(stats['bytes'])} in {elapsed:.0f}s)")
            except Exception as e:
                stats["errors"] += 1
                print(f"[{i:>3}/{len(dates)}] {d}  ERROR   download: {e}")
                if dest.exists():
                    dest.unlink()

            time.sleep(rate_limit)

    except KeyboardInterrupt:
        print("\n\nInterrupted by user. Re-run the script to resume.")

    elapsed = time.monotonic() - t_start
    print()
    print("=" * 70)
    print(f"Done in {elapsed/60:.1f} min")
    print(f"  Downloaded:  {stats['downloaded']:>4} files  ({fmt_size(stats['bytes'])})")
    print(f"  Skipped:     {stats['skipped']:>4} files (already on disk)")
    print(f"  No data:     {stats['no_data']:>4} dates (weekends/holidays/before cutoff)")
    print(f"  Errors:      {stats['errors']:>4}")
    print("=" * 70)


if __name__ == "__main__":
    main()
