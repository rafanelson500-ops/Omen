"""OOS baseline run — saves trade log + equity to CSV.

Same locked config as run_backtest.py on main. Only difference: writes outputs.

Usage: python3.11 scripts/run_oos_baseline.py
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

START = date(2025, 9, 8)
END = date(2025, 12, 23)
FREQ = "5min"
Z_THRESHOLD = 1.8
BLACKOUT_LUNCH = True

OUT_DIR = Path("/Users/rafanelson/Omen/backend/data/analysis")
OUT_TRADES = OUT_DIR / "oos_baseline_trades_2025-09-08_2025-12-23.csv"
OUT_EQUITY = OUT_DIR / "oos_baseline_equity_2025-09-08_2025-12-23.csv"


def main() -> None:
    console.print("[bold cyan]=== OOS BASELINE RUN ===[/]")
    console.print(f"Window: {START} -> {END} @ {FREQ}")
    console.print(f"z_threshold={Z_THRESHOLD}  blackout_lunch={BLACKOUT_LUNCH}")
    console.print()

    cfg = BacktestConfig(bar_freq=FREQ)
    console.print(f"Locked exits: stop={cfg.exits.stop_atr_mult}xATR  "
                  f"target={cfg.exits.target_atr_mult}xATR  "
                  f"atr_window={cfg.exits.atr_window_bars}  "
                  f"time_stop={cfg.exits.time_stop_min}min  "
                  f"trail={cfg.exits.trail_after_r}")
    console.print(f"Locked feature_lookback_bars={cfg.feature_lookback_bars}")
    console.print()

    days = gex.rth_sessions(START, END)
    console.print(f"Sessions: {len(days)}")

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

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    trades.to_csv(OUT_TRADES, index=False)
    equity.to_csv(OUT_EQUITY, index=True)
    console.print(f"[green]Saved:[/] {OUT_TRADES.name}")
    console.print(f"[green]Saved:[/] {OUT_EQUITY.name}")
    console.print(f"[green]Trades:[/] {len(trades)}")
    console.print()

    summ = metrics.summarize(trades, equity)
    t = Table(title="OOS flow_burst summary", show_header=False, box=None)
    t.add_column(style="bold cyan"); t.add_column()
    for k, v in summ.items():
        fmt = f"{v:,.4f}" if isinstance(v, float) else str(v)
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
