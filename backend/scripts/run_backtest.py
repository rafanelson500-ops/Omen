"""Run a backtest from CLI. Mirrors the Streamlit app but outputs to terminal.

Example:
    python scripts/run_backtest.py --strategy flow_burst --days 80 --freq 1min
    python scripts/run_backtest.py --strategy wall_reject --start 2026-02-01 --end 2026-04-21
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from rich.console import Console
from rich.table import Table

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cheese import backtest, features, gex, market, metrics, strategy  # noqa: E402
from cheese.config import BacktestConfig  # noqa: E402

console = Console()


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--strategy", required=True, choices=list(strategy.ALL_STRATEGIES.keys()))
    p.add_argument("--days", type=int, default=80)
    p.add_argument("--start", type=str)
    p.add_argument("--end", type=str)
    p.add_argument("--freq", type=str, default="1min", choices=["1min", "5min"])
    p.add_argument("--z-threshold", type=float, default=2.0,
                   help="(flow_burst) z-score threshold for entries")
    p.add_argument("--min-flow-z", type=float, default=1.0,
                   help="(wall_break) min |gexoflow_z| to confirm break")
    return p.parse_args()


def main() -> None:
    args = _parse_args()
    if args.start:
        start = date.fromisoformat(args.start)
        end = date.fromisoformat(args.end) if args.end else date.today()
        days = gex.rth_sessions(start, end)
    else:
        days = gex.last_n_sessions(args.days)
        start, end = days[0], days[-1]

    console.print(f"[bold]range:[/] {start} -> {end}  ({len(days)} sessions) @ {args.freq}")

    mkt = market.load(start, end, freq=args.freq, rth_only=True)
    gex_raw = gex.load_range(days)
    if gex_raw.empty:
        console.print("[red]No GEX data found. Run scripts/fetch_gex.py first.[/]")
        sys.exit(1)
    gex_bars = gex.resample(gex_raw, freq=args.freq)
    feat = features.build_features(mkt, gex_bars)

    strat_cls = strategy.ALL_STRATEGIES[args.strategy]
    kwargs = {}
    if args.strategy == "flow_burst":
        kwargs["z_threshold"] = args.z_threshold
    elif args.strategy == "wall_break":
        kwargs["min_flow_z"] = args.min_flow_z
    strat = strat_cls(**kwargs)

    signals = strat.signals(feat)
    trades, equity = backtest.run(feat, signals, strategy_name=args.strategy, cfg=BacktestConfig(bar_freq=args.freq))

    _print_summary(args.strategy, trades, equity)


def _print_summary(name: str, trades, equity) -> None:
    summ = metrics.summarize(trades, equity)
    t = Table(title=f"{name} summary", show_header=False, box=None)
    t.add_column(style="bold cyan"); t.add_column()
    for k, v in summ.items():
        fmt = f"{v:,.2f}" if isinstance(v, float) else str(v)
        t.add_row(k, fmt)
    console.print(t)

    if not trades.empty:
        rb = metrics.regime_breakdown(trades)
        if not rb.empty:
            console.print("\n[bold]regime breakdown[/]")
            console.print(rb.to_string(index=False))
        eb = metrics.exit_reason_breakdown(trades)
        if not eb.empty:
            console.print("\n[bold]exit reason breakdown[/]")
            console.print(eb.to_string(index=False))


if __name__ == "__main__":
    main()
