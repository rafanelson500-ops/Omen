"""OOS VIX bucket breakdown — descriptive only, with 0DTE confound check.

Reads: data/analysis/oos_baseline_trades_2025-09-08_2025-12-23.csv
Pulls: ^VIX from yfinance for the OOS window
Joins: prior-day VIX close to each trade entry date
Writes: data/analysis/oos_vix_breakdown.csv
        diagnostics/oos_75d_baseline/vix_breakdown.md

NO strategy changes, NO filter testing.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf
from rich.console import Console
from rich.table import Table

console = Console()

INPUT_CSV = Path("/Users/rafanelson/Omen/backend/data/analysis/oos_baseline_trades_2025-09-08_2025-12-23.csv")
OUTPUT_CSV = Path("/Users/rafanelson/Omen/backend/data/analysis/oos_vix_breakdown.csv")
OUTPUT_MD = Path("/Users/rafanelson/Omen/diagnostics/oos_75d_baseline/vix_breakdown.md")

VIX_BUCKETS = [
    ("low",      lambda v: v < 15),
    ("low_mid",  lambda v: 15 <= v < 18),
    ("mid",      lambda v: 18 <= v < 20),
    ("elevated", lambda v: 20 <= v < 25),
    ("high",     lambda v: v >= 25),
]

# In-sample reference for direct comparison
IS_REFERENCE = {
    "low":      {"n": 21, "sharpe": 0.025, "pnl": 195.0,    "wr": 0.333},
    "low_mid":  {"n": 55, "sharpe": 0.077, "pnl": 2131.0,   "wr": 0.400},
    "mid":      {"n": 29, "sharpe": 0.034, "pnl": 486.0,    "wr": 0.448},
    "elevated": {"n": 40, "sharpe": 0.574, "pnl": 18006.0,  "wr": 0.725},
    "high":     {"n": 29, "sharpe": 0.158, "pnl": 3830.0,   "wr": 0.483},
}

ZERO_DTE_DAYS = {0, 2, 4}  # Mon=0, Wed=2, Fri=4 (pandas day-of-week)


def bucket_for(vix: float) -> str:
    for name, fn in VIX_BUCKETS:
        if fn(vix):
            return name
    return "unknown"


def main() -> None:
    if not INPUT_CSV.exists():
        console.print(f"[red]Trade log not found: {INPUT_CSV}[/]")
        sys.exit(1)

    trades = pd.read_csv(INPUT_CSV)
    trades["entry_time"] = pd.to_datetime(trades["entry_time"], utc=True).dt.tz_convert("America/New_York")
    trades["entry_date"] = trades["entry_time"].dt.date
    trades["dow"] = trades["entry_time"].dt.dayofweek
    trades["is_0dte_day"] = trades["dow"].isin(ZERO_DTE_DAYS)
    console.print(f"[bold]Loaded:[/] {len(trades)} OOS trades")

    # Pull VIX with a buffer for prior-day join
    console.print(f"[dim]Pulling ^VIX from yfinance ({trades['entry_date'].min()} → {trades['entry_date'].max()})...[/]")
    vix = yf.Ticker("^VIX").history(
        start="2025-08-25",
        end="2025-12-31",
        interval="1d",
        auto_adjust=False,
    )
    if vix.empty:
        console.print("[red]No VIX data returned from yfinance[/]")
        sys.exit(1)
    vix_close = vix["Close"].copy()
    vix_close.index = pd.to_datetime(vix_close.index).date
    vix_df = pd.DataFrame({"vix": vix_close.values}, index=vix_close.index).sort_index()
    vix_df["prior_vix"] = vix_df["vix"].shift(1)
    console.print(f"[dim]VIX rows: {len(vix_df)}, prior_vix non-null: {vix_df['prior_vix'].notna().sum()}[/]")
    console.print(f"[dim]VIX range over period: {vix_df['vix'].min():.2f} - {vix_df['vix'].max():.2f}[/]")

    # Join prior-day VIX to each trade
    trades = trades.merge(
        vix_df[["prior_vix"]],
        how="left",
        left_on="entry_date",
        right_index=True,
    )
    pre_drop = len(trades)
    trades = trades.dropna(subset=["prior_vix"])
    if len(trades) < pre_drop:
        console.print(f"[yellow]Dropped {pre_drop - len(trades)} trades with no prior VIX (probably first session)[/]")

    trades["vix_bucket"] = trades["prior_vix"].apply(bucket_for)
    console.print()

    # Per-bucket breakdown
    rows = []
    for name, _ in VIX_BUCKETS:
        sub = trades[trades["vix_bucket"] == name]
        n = len(sub)
        if n == 0:
            rows.append({"bucket": name, "n": 0, "win_rate": np.nan, "expectancy": np.nan,
                         "total_pnl": 0.0, "per_trade_sharpe": np.nan,
                         "is_n": IS_REFERENCE[name]["n"], "is_sharpe": IS_REFERENCE[name]["sharpe"],
                         "is_pnl": IS_REFERENCE[name]["pnl"]})
            continue
        wins = (sub["net_dollars"] > 0).sum()
        wr = wins / n
        mean = sub["net_dollars"].mean()
        std = sub["net_dollars"].std(ddof=1) if n > 1 else np.nan
        sharpe = mean / std if std and std > 0 else np.nan
        rows.append({
            "bucket": name, "n": n,
            "win_rate": round(wr, 4),
            "expectancy": round(mean, 2),
            "total_pnl": round(sub["net_dollars"].sum(), 2),
            "per_trade_sharpe": round(sharpe, 4) if pd.notna(sharpe) else np.nan,
            "is_n": IS_REFERENCE[name]["n"],
            "is_sharpe": IS_REFERENCE[name]["sharpe"],
            "is_pnl": IS_REFERENCE[name]["pnl"],
        })

    df = pd.DataFrame(rows)

    # Print main table
    t = Table(title="OOS VIX Bucket Breakdown vs In-Sample")
    t.add_column("Bucket", style="bold cyan")
    t.add_column("n", justify="right")
    t.add_column("WinRate", justify="right")
    t.add_column("Expectancy", justify="right")
    t.add_column("OOS Total", justify="right", style="bold")
    t.add_column("OOS Sharpe", justify="right")
    t.add_column("IS n", justify="right", style="dim")
    t.add_column("IS Sharpe", justify="right", style="dim")
    t.add_column("IS Total", justify="right", style="dim")
    for r in rows:
        t.add_row(
            r["bucket"], str(r["n"]),
            f"{r['win_rate']:.3f}" if pd.notna(r["win_rate"]) else "—",
            f"${r['expectancy']:,.2f}" if pd.notna(r["expectancy"]) else "—",
            f"${r['total_pnl']:,.2f}",
            f"{r['per_trade_sharpe']:.3f}" if pd.notna(r["per_trade_sharpe"]) else "—",
            str(r["is_n"]),
            f"{r['is_sharpe']:.3f}",
            f"${r['is_pnl']:,.0f}",
        )
    console.print(t)

    # CONFOUND CHECK: VIX 20-25 split by 0DTE day
    elev = trades[trades["vix_bucket"] == "elevated"]
    if len(elev) > 0:
        console.print()
        console.print("[bold yellow]Confound check — VIX 20-25 bucket split by 0DTE day:[/]")
        for is_0dte in [True, False]:
            sub = elev[elev["is_0dte_day"] == is_0dte]
            n = len(sub)
            if n == 0:
                continue
            wr = (sub["net_dollars"] > 0).sum() / n
            mean = sub["net_dollars"].mean()
            tot = sub["net_dollars"].sum()
            std = sub["net_dollars"].std(ddof=1) if n > 1 else np.nan
            sh = mean / std if std and std > 0 else np.nan
            label = "0DTE (Mon/Wed/Fri)" if is_0dte else "non-0DTE (Tue/Thu)"
            console.print(f"  VIX 20-25 × {label}: n={n}, wr={wr:.3f}, mean=${mean:,.2f}, total=${tot:,.2f}, sharpe={sh:.3f}")

    # Save
    df.to_csv(OUTPUT_CSV, index=False)
    OUTPUT_MD.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_MD, "w") as f:
        f.write("# OOS VIX Bucket Breakdown\n\n")
        f.write(f"Total OOS trades after VIX join: {len(trades)}\n")
        f.write(f"VIX range over OOS period: {vix_df['vix'].min():.2f} - {vix_df['vix'].max():.2f}\n\n")
        f.write("## Per-bucket\n\n")
        f.write(df.to_csv(index=False))
        f.write("\n\n## Confound check (VIX 20-25 × 0DTE)\n\n")
        for is_0dte in [True, False]:
            sub = elev[elev["is_0dte_day"] == is_0dte] if len(elev) > 0 else pd.DataFrame()
            if len(sub) == 0:
                continue
            label = "0DTE" if is_0dte else "non-0DTE"
            f.write(f"- VIX 20-25 × {label}: n={len(sub)}, total=${sub['net_dollars'].sum():,.2f}\n")
    console.print()
    console.print(f"[green]Saved:[/] {OUTPUT_CSV.name}")
    console.print(f"[green]Saved:[/] {OUTPUT_MD}")


if __name__ == "__main__":
    main()
