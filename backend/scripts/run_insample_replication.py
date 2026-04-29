"""In-sample replication test — verify wrapper reproduces Sharpe 4.45.

Same locked config as run_oos_baseline.py. Only difference: in-sample dates.
If this returns Sharpe ~4.45, the OOS degradation is real.
If this returns something different, the wrapper has a bug.
"""
from __future__ import annotations

import sys
from pathlib import Path
from datetime import date

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cheese import backtest, features, gex, market, metrics, strategy
from cheese.config import BacktestConfig
from rich.console import Console
from rich.table import Table

console = Console()

START = date(2025, 12, 26)
END = date(2026, 4, 22)
FREQ = "5min"
Z_THRESHOLD = 1.8
BLACKOUT_LUNCH = True


def main() -> None:
    console.print("[bold cyan]=== IN-SAMPLE REPLICATION ===[/]")
    console.print(f"Window: {START} -> {END} @ {FREQ}")
    console.print(f"Expected: Sharpe ~4.45, ~174 trades, +$24,649 PnL")
    console.print()

    cfg = BacktestConfig(bar_freq=FREQ)
    days = gex.rth_sessions(START, END)
    console.print(f"Sessions: {len(days)} (expected 80)")

    mkt = market.load(START, END, freq=FREQ, rth_only=True)
    gex_raw = gex.load_range(days)
    if gex_raw.empty:
        console.print("[red]No GEX data found.[/]")
        sys.exit(1)
    gex_bars = gex.resample(gex_raw, freq=FREQ)
    feat = features.build_features(mkt, gex_bars)

    strat = strategy.FlowBurstStrategy(
        z_threshold=Z_THRESHOLD,
        blackout_lunch=BLACKOUT_LUNCH,
    )
    signals = strat.signals(feat)
    trades, equity = backtest.run(feat, signals, strategy_name="flow_burst", cfg=cfg)

    console.print(f"\n[bold]Trades:[/] {len(trades)} (expected ~174)")
    summ = metrics.summarize(trades, equity)
    t = Table(title="In-sample replication summary", show_header=False, box=None)
    t.add_column(style="bold cyan"); t.add_column()
    for k, v in summ.items():
        fmt = f"{v:,.4f}" if isinstance(v, float) else str(v)
        t.add_row(k, fmt)
    console.print(t)


if __name__ == "__main__":
    main()
