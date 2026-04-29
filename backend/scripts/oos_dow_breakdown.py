"""OOS day-of-week breakdown — descriptive only.

Reads: data/analysis/oos_baseline_trades_2025-09-08_2025-12-23.csv
Writes: data/analysis/oos_dow_breakdown.csv
        diagnostics/oos_75d_baseline/dow_breakdown.md

Slices OOS trades by entry day. NO strategy changes, NO filter testing.
Just descriptive comparison vs in-sample 0DTE thesis.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from rich.console import Console
from rich.table import Table

console = Console()

INPUT_CSV = Path("/Users/rafanelson/Omen/backend/data/analysis/oos_baseline_trades_2025-09-08_2025-12-23.csv")
OUTPUT_CSV = Path("/Users/rafanelson/Omen/backend/data/analysis/oos_dow_breakdown.csv")
OUTPUT_MD = Path("/Users/rafanelson/Omen/diagnostics/oos_75d_baseline/dow_breakdown.md")

DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
ZERO_DTE_DAYS = {"Monday", "Wednesday", "Friday"}

# In-sample reference (for direct comparison)
IS_REFERENCE = {
    "Monday":    {"pnl": 1074.0,  "is_0dte": True,  "note": "weak (anomaly)"},
    "Tuesday":   {"pnl": 1571.0,  "is_0dte": False, "note": "weak"},
    "Wednesday": {"pnl": 9792.0,  "is_0dte": True,  "note": "strongest"},
    "Thursday":  {"pnl": 3924.0,  "is_0dte": False, "note": "medium"},
    "Friday":    {"pnl": 8287.0,  "is_0dte": True,  "note": "strong"},
}


def main() -> None:
    if not INPUT_CSV.exists():
        console.print(f"[red]Trade log not found: {INPUT_CSV}[/]")
        sys.exit(1)

    trades = pd.read_csv(INPUT_CSV)
    console.print(f"[bold]Loaded:[/] {len(trades)} OOS trades")

    # Detect entry-time column
    candidates = ["entry_time", "entry_ts", "entry_timestamp", "entry"]
    entry_col = next((c for c in candidates if c in trades.columns), None)
    if entry_col is None:
        console.print(f"[red]No entry time column found. Available: {list(trades.columns)}[/]")
        sys.exit(1)
    console.print(f"[dim]Using entry column: {entry_col}[/]")

    trades[entry_col] = pd.to_datetime(trades[entry_col], utc=True).dt.tz_convert("America/New_York")
    trades["day_of_week"] = trades[entry_col].dt.day_name()
    trades["is_0dte_day"] = trades["day_of_week"].isin(ZERO_DTE_DAYS)

    # Per-day breakdown
    rows = []
    for day in DAY_NAMES:
        sub = trades[trades["day_of_week"] == day]
        n = len(sub)
        if n == 0:
            rows.append({
                "day": day, "is_0dte": day in ZERO_DTE_DAYS,
                "n": 0, "win_rate": np.nan, "expectancy": np.nan,
                "total_pnl": 0.0, "per_trade_sharpe": np.nan,
                "in_sample_pnl": IS_REFERENCE[day]["pnl"],
            })
            continue
        wins = (sub["net_dollars"] > 0).sum()
        win_rate = wins / n
        mean = sub["net_dollars"].mean()
        std = sub["net_dollars"].std(ddof=1) if n > 1 else np.nan
        sharpe = (mean / std) if (std and std > 0) else np.nan
        rows.append({
            "day": day,
            "is_0dte": day in ZERO_DTE_DAYS,
            "n": n,
            "win_rate": round(win_rate, 4),
            "expectancy": round(mean, 2),
            "total_pnl": round(sub["net_dollars"].sum(), 2),
            "per_trade_sharpe": round(sharpe, 4) if pd.notna(sharpe) else np.nan,
            "in_sample_pnl": IS_REFERENCE[day]["pnl"],
        })

    df = pd.DataFrame(rows)

    # Print table
    t = Table(title="OOS Day-of-Week Breakdown vs In-Sample")
    t.add_column("Day", style="bold cyan")
    t.add_column("0DTE", justify="center")
    t.add_column("n", justify="right")
    t.add_column("WinRate", justify="right")
    t.add_column("Expectancy", justify="right")
    t.add_column("OOS Total", justify="right", style="bold")
    t.add_column("PerTradeSharpe", justify="right")
    t.add_column("IS Total", justify="right", style="dim")
    for r in rows:
        t.add_row(
            r["day"],
            "Y" if r["is_0dte"] else "—",
            str(r["n"]),
            f"{r['win_rate']:.3f}" if pd.notna(r["win_rate"]) else "—",
            f"${r['expectancy']:,.2f}" if pd.notna(r["expectancy"]) else "—",
            f"${r['total_pnl']:,.2f}",
            f"{r['per_trade_sharpe']:.3f}" if pd.notna(r["per_trade_sharpe"]) else "—",
            f"${r['in_sample_pnl']:,.0f}",
        )
    console.print(t)

    # 0DTE vs non-0DTE summary
    zdte = trades[trades["is_0dte_day"]]
    non = trades[~trades["is_0dte_day"]]
    z_total = zdte["net_dollars"].sum()
    n_total = non["net_dollars"].sum()
    grand = trades["net_dollars"].sum()

    console.print()
    console.print("[bold]0DTE concentration check:[/]")
    if grand != 0:
        console.print(f"  0DTE days (Mon/Wed/Fri):     {len(zdte)} trades, ${z_total:,.2f} ({z_total/grand*100:.1f}% of OOS PnL)")
        console.print(f"  Non-0DTE days (Tue/Thu):     {len(non)} trades, ${n_total:,.2f} ({n_total/grand*100:.1f}% of OOS PnL)")
    else:
        console.print(f"  0DTE: {len(zdte)} trades, ${z_total:,.2f}")
        console.print(f"  Non-0DTE: {len(non)} trades, ${n_total:,.2f}")
    console.print(f"  In-sample reference: 0DTE = $19,153 (78% of IS PnL), non-0DTE = $5,495 (22%)")

    # Save outputs
    df.to_csv(OUTPUT_CSV, index=False)
    OUTPUT_MD.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_MD, "w") as f:
        f.write("# OOS Day-of-Week Breakdown\n\n")
        f.write(f"**Source:** `{INPUT_CSV.name}`\n")
        f.write(f"**Total OOS trades:** {len(trades)}\n\n")
        f.write("## Per-day results\n\n")
        f.write(df.to_markdown(index=False))
        f.write("\n\n## 0DTE concentration\n\n")
        if grand != 0:
            f.write(f"- 0DTE days (Mon/Wed/Fri): {len(zdte)} trades, ${z_total:,.2f} ({z_total/grand*100:.1f}%)\n")
            f.write(f"- Non-0DTE (Tue/Thu): {len(non)} trades, ${n_total:,.2f} ({n_total/grand*100:.1f}%)\n")
        f.write(f"- In-sample reference: 0DTE = 78%, non-0DTE = 22%\n")
    console.print(f"\n[green]Saved:[/] {OUTPUT_CSV.name}")
    console.print(f"[green]Saved:[/] {OUTPUT_MD}")


if __name__ == "__main__":
    main()
