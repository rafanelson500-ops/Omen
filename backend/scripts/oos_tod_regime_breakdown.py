"""OOS time-of-day + side×regime breakdown — descriptive only.

Reads: data/analysis/oos_baseline_trades_2025-09-08_2025-12-23.csv
Writes: data/analysis/oos_tod_breakdown.csv
        data/analysis/oos_side_regime_breakdown.csv
        diagnostics/oos_75d_baseline/tod_regime_breakdown.md

NO strategy changes, NO filter testing.
"""
from __future__ import annotations

import sys
from datetime import time
from pathlib import Path

import numpy as np
import pandas as pd
from rich.console import Console
from rich.table import Table

console = Console()

INPUT_CSV = Path("/Users/rafanelson/Omen/backend/data/analysis/oos_baseline_trades_2025-09-08_2025-12-23.csv")
OUT_TOD = Path("/Users/rafanelson/Omen/backend/data/analysis/oos_tod_breakdown.csv")
OUT_SR = Path("/Users/rafanelson/Omen/backend/data/analysis/oos_side_regime_breakdown.csv")
OUTPUT_MD = Path("/Users/rafanelson/Omen/diagnostics/oos_75d_baseline/tod_regime_breakdown.md")

TOD_BUCKETS = [
    ("opening_drive", time(9, 30),  time(10, 0)),
    ("morning_2",     time(10, 0),  time(10, 30)),
    ("lunch",         time(10, 30), time(12, 30)),
    ("afternoon_1",   time(12, 30), time(14, 0)),
    ("afternoon_2",   time(14, 0),  time(15, 30)),
    ("closing_drive", time(15, 30), time(16, 1)),
]

# In-sample reference for time-of-day
IS_TOD = {
    "opening_drive": {"n": 39,  "sharpe": 0.091,  "pnl": 3068.0},
    "morning_2":     {"n": 1,   "sharpe": np.nan, "pnl": -205.0},
    "lunch":         {"n": 0,   "sharpe": np.nan, "pnl": 0.0},
    "afternoon_1":   {"n": 22,  "sharpe": 0.521,  "pnl": 5615.0},
    "afternoon_2":   {"n": 107, "sharpe": 0.232,  "pnl": 14640.0},
    "closing_drive": {"n": 5,   "sharpe": 0.630,  "pnl": 1531.0},
}


def bucket_for_time(t: time) -> str:
    for name, lo, hi in TOD_BUCKETS:
        if lo <= t < hi:
            return name
    return "unknown"


def stats_row(name: str, sub: pd.DataFrame, ref: dict | None = None) -> dict:
    n = len(sub)
    if n == 0:
        row = {"bucket": name, "n": 0, "win_rate": np.nan, "expectancy": np.nan,
               "total_pnl": 0.0, "per_trade_sharpe": np.nan}
    else:
        wins = (sub["net_dollars"] > 0).sum()
        wr = wins / n
        mean = sub["net_dollars"].mean()
        std = sub["net_dollars"].std(ddof=1) if n > 1 else np.nan
        sharpe = mean / std if std and std > 0 else np.nan
        row = {
            "bucket": name, "n": n,
            "win_rate": round(wr, 4),
            "expectancy": round(mean, 2),
            "total_pnl": round(sub["net_dollars"].sum(), 2),
            "per_trade_sharpe": round(sharpe, 4) if pd.notna(sharpe) else np.nan,
        }
    if ref:
        row["is_n"] = ref["n"]
        row["is_sharpe"] = ref["sharpe"]
        row["is_pnl"] = ref["pnl"]
    return row


def main() -> None:
    if not INPUT_CSV.exists():
        console.print(f"[red]Trade log not found: {INPUT_CSV}[/]")
        sys.exit(1)

    trades = pd.read_csv(INPUT_CSV)
    trades["entry_time"] = pd.to_datetime(trades["entry_time"], utc=True).dt.tz_convert("America/New_York")
    trades["entry_clock"] = trades["entry_time"].dt.time
    trades["tod_bucket"] = trades["entry_clock"].apply(bucket_for_time)
    console.print(f"[bold]Loaded:[/] {len(trades)} OOS trades")
    console.print()

    # ============================================================
    # CUT A — Time of day
    # ============================================================
    tod_rows = []
    for name, _, _ in TOD_BUCKETS:
        sub = trades[trades["tod_bucket"] == name]
        tod_rows.append(stats_row(name, sub, IS_TOD.get(name)))

    t = Table(title="OOS Time-of-Day Breakdown vs In-Sample")
    t.add_column("Bucket", style="bold cyan")
    t.add_column("n", justify="right")
    t.add_column("WinRate", justify="right")
    t.add_column("Expectancy", justify="right")
    t.add_column("OOS Total", justify="right", style="bold")
    t.add_column("OOS Sharpe", justify="right")
    t.add_column("IS n", justify="right", style="dim")
    t.add_column("IS Sharpe", justify="right", style="dim")
    t.add_column("IS Total", justify="right", style="dim")
    for r in tod_rows:
        t.add_row(
            r["bucket"], str(r["n"]),
            f"{r['win_rate']:.3f}" if pd.notna(r["win_rate"]) else "—",
            f"${r['expectancy']:,.2f}" if pd.notna(r["expectancy"]) else "—",
            f"${r['total_pnl']:,.2f}",
            f"{r['per_trade_sharpe']:.3f}" if pd.notna(r.get("per_trade_sharpe", np.nan)) else "—",
            str(r.get("is_n", "—")),
            f"{r['is_sharpe']:.3f}" if pd.notna(r.get("is_sharpe", np.nan)) else "—",
            f"${r.get('is_pnl', 0):,.0f}",
        )
    console.print(t)
    pd.DataFrame(tod_rows).to_csv(OUT_TOD, index=False)
    console.print(f"[green]Saved:[/] {OUT_TOD.name}")
    console.print()

    # ============================================================
    # CUT B — Side × Gamma Regime
    # ============================================================
    console.print("[bold yellow]Side × Gamma Regime breakdown[/]")
    sr_rows = []
    for side in ["long", "short"]:
        for regime in ["long", "short"]:
            sub = trades[(trades["side"] == (1 if side == "long" else -1)) & (trades["gamma_regime"] == regime)]
            label = f"{side.upper()} side × {regime}-gamma"
            sr_rows.append(stats_row(label, sub))

    # Also marginals (already known but good to print together)
    for side in ["long", "short"]:
        sub = trades[trades["side"] == (1 if side == "long" else -1)]
        label = f"{side.upper()} side (all regimes)"
        sr_rows.append(stats_row(label, sub))
    for regime in ["long", "short"]:
        sub = trades[trades["gamma_regime"] == regime]
        label = f"BOTH sides × {regime}-gamma"
        sr_rows.append(stats_row(label, sub))

    t2 = Table(title="OOS Side × Regime Breakdown")
    t2.add_column("Slice", style="bold cyan")
    t2.add_column("n", justify="right")
    t2.add_column("WinRate", justify="right")
    t2.add_column("Expectancy", justify="right")
    t2.add_column("Total PnL", justify="right", style="bold")
    t2.add_column("Sharpe", justify="right")
    for r in sr_rows:
        t2.add_row(
            r["bucket"], str(r["n"]),
            f"{r['win_rate']:.3f}" if pd.notna(r["win_rate"]) else "—",
            f"${r['expectancy']:,.2f}" if pd.notna(r["expectancy"]) else "—",
            f"${r['total_pnl']:,.2f}",
            f"{r['per_trade_sharpe']:.3f}" if pd.notna(r.get("per_trade_sharpe", np.nan)) else "—",
        )
    console.print(t2)
    pd.DataFrame(sr_rows).to_csv(OUT_SR, index=False)
    console.print(f"[green]Saved:[/] {OUT_SR.name}")

    # Save markdown
    OUTPUT_MD.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_MD, "w") as f:
        f.write("# OOS Time-of-Day + Side×Regime Breakdown\n\n")
        f.write(f"Total OOS trades: {len(trades)}\n\n")
        f.write("## Time of day\n\n")
        f.write(pd.DataFrame(tod_rows).to_csv(index=False))
        f.write("\n\n## Side × Regime\n\n")
        f.write(pd.DataFrame(sr_rows).to_csv(index=False))
    console.print(f"[green]Saved:[/] {OUTPUT_MD}")


if __name__ == "__main__":
    main()
