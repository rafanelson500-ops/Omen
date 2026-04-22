"""Fetch N trading days of GEXbot orderflow for ES_SPX and cache as parquet.

Usage:
    python scripts/fetch_gex.py --days 80
    python scripts/fetch_gex.py --start 2026-01-02 --end 2026-04-21
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date
from pathlib import Path

from dotenv import load_dotenv
from rich.console import Console

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cheese import gex  # noqa: E402

console = Console()


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Fetch GEXbot ES_SPX orderflow history")
    p.add_argument("--days", type=int, default=80, help="Last N RTH trading days")
    p.add_argument("--start", type=str, help="YYYY-MM-DD (overrides --days)")
    p.add_argument("--end", type=str, help="YYYY-MM-DD (defaults to today ET)")
    p.add_argument("--force", action="store_true", help="Re-download cached days")
    return p.parse_args()


def main() -> None:
    load_dotenv()
    args = _parse_args()
    api_key = os.getenv("GEXBOT_API_KEY")
    if not api_key:
        console.print("[red]GEXBOT_API_KEY missing in .env[/]")
        sys.exit(1)

    if args.start:
        start = date.fromisoformat(args.start)
        end = date.fromisoformat(args.end) if args.end else date.today()
    else:
        days = gex.last_n_sessions(args.days)
        start, end = days[0], days[-1]

    console.print(f"[bold]GEXbot range:[/] {start.isoformat()} -> {end.isoformat()}")
    results = gex.fetch_range(start, end, api_key=api_key, force=args.force)
    ok = sum(1 for v in results.values() if v is not None)
    console.print(f"[bold green]done:[/] {ok}/{len(results)} days cached")


if __name__ == "__main__":
    main()
