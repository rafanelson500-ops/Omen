"""Fetch ES.c.0 ohlcv-1s from Databento and cache as parquet.

Prints an estimated USD cost and asks for confirmation before downloading
(use --yes to auto-confirm). One contiguous pull for the full window; cached
file is keyed on (start, end) so subsequent runs are free.

Usage:
    python scripts/fetch_market.py --days 80
    python scripts/fetch_market.py --start 2026-01-02 --end 2026-04-21 --yes
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

from cheese import gex, market  # noqa: E402

console = Console()


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Fetch ES.c.0 1s OHLCV from Databento")
    p.add_argument("--days", type=int, default=80, help="Last N RTH trading days")
    p.add_argument("--start", type=str, help="YYYY-MM-DD (overrides --days)")
    p.add_argument("--end", type=str, help="YYYY-MM-DD (defaults to today ET)")
    p.add_argument("--yes", action="store_true", help="Skip cost confirmation")
    p.add_argument("--force", action="store_true", help="Re-download cached range")
    return p.parse_args()


def main() -> None:
    load_dotenv()
    args = _parse_args()
    api_key = os.getenv("DATABENTO_API_KEY")
    if not api_key:
        console.print("[red]DATABENTO_API_KEY missing in .env[/]")
        sys.exit(1)

    if args.start:
        start = date.fromisoformat(args.start)
        end = date.fromisoformat(args.end) if args.end else date.today()
    else:
        days = gex.last_n_sessions(args.days)
        start, end = days[0], days[-1]

    console.print(f"[bold]Databento range:[/] {start.isoformat()} -> {end.isoformat()}")
    try:
        cost = market.estimate_cost(start, end, api_key)
        console.print(f"[bold yellow]Estimated Databento cost: ${cost:.4f}[/]")
    except Exception as e:  # noqa: BLE001
        console.print(f"[yellow]could not estimate cost ({e!r}); proceeding[/]")
        cost = None

    if not args.yes and cost is not None and cost > 0.10:
        ans = input("proceed with download? [y/N] ").strip().lower()
        if ans not in {"y", "yes"}:
            console.print("[dim]aborted.[/]")
            return

    path = market.fetch(start, end, api_key=api_key, force=args.force)
    console.print(f"[bold green]done:[/] {path}")


if __name__ == "__main__":
    main()
