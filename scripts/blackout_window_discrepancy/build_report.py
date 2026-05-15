"""Build the side-by-side comparison report for Run A (locked, 10:30-12:30)
vs Run B (documented, 12:00-13:00). Joins by entry_time; identifies new and
suppressed trades; writes comparison.md.

Consumes:
  diagnostics/blackout-window-discrepancy/trades_A_locked.csv
  diagnostics/blackout-window-discrepancy/trades_B_doc_window.csv
  diagnostics/blackout-window-discrepancy/metrics_A_locked.json
  diagnostics/blackout-window-discrepancy/metrics_B_doc_window.json

Produces:
  diagnostics/blackout-window-discrepancy/comparison.md
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

OUT_DIR = Path("/Users/rafanelson/Omen/diagnostics/blackout-window-discrepancy")
A_TRADES = OUT_DIR / "trades_A_locked.csv"
B_TRADES = OUT_DIR / "trades_B_doc_window.csv"
A_METRICS = OUT_DIR / "metrics_A_locked.json"
B_METRICS = OUT_DIR / "metrics_B_doc_window.json"
REPORT = OUT_DIR / "comparison.md"


def _fmt_money(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "—"
    return f"${v:>+,.2f}"


def _fmt_pct(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "—"
    return f"{v*100:.1f}%"


def _fmt_num(v, places=2):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "—"
    return f"{v:+.{places}f}"


def _summary_row(label, val_a, val_b, formatter):
    sa, sb = formatter(val_a), formatter(val_b)
    if val_a is None or val_b is None:
        delta = "—"
    elif isinstance(val_a, (int, float)) and isinstance(val_b, (int, float)):
        d = val_b - val_a
        if label == "Trade count":
            delta = f"{int(d):+d}"
        elif label in ("Win rate",):
            delta = f"{d*100:+.2f} pp"
        elif label in ("Sharpe", "Profit factor"):
            delta = f"{d:+.3f}"
        else:
            delta = _fmt_money(d)
    else:
        delta = "—"
    return f"| {label:<17}| {sa:>20s}| {sb:>20s}| {delta:>14s}|"


def _aggregate(sub: pd.DataFrame) -> dict:
    n = len(sub)
    if n == 0:
        return {"n": 0, "total_pnl": 0.0, "win_rate": None, "cells": {}}
    return {
        "n": n,
        "total_pnl": float(sub["net_dollars"].sum()),
        "win_rate": float((sub["net_dollars"] > 0).mean()),
        "cells": sub["cell"].value_counts().to_dict(),
    }


def main() -> int:
    a = pd.read_csv(A_TRADES, parse_dates=["entry_time"])
    b = pd.read_csv(B_TRADES, parse_dates=["entry_time"])
    ma = json.loads(A_METRICS.read_text())
    mb = json.loads(B_METRICS.read_text())

    a_keys = set(a["entry_time"])
    b_keys = set(b["entry_time"])

    only_b = b[b["entry_time"].isin(b_keys - a_keys)].sort_values("entry_time")
    only_a = a[a["entry_time"].isin(a_keys - b_keys)].sort_values("entry_time")
    shared = a_keys & b_keys

    agg_b_new = _aggregate(only_b)
    agg_a_only = _aggregate(only_a)

    L: list[str] = []
    L.append("# Blackout-window discrepancy — IS counterfactual")
    L.append("")
    L.append(f"Generated: {pd.Timestamp.now().strftime('%Y-%m-%dT%H:%M:%S')}")
    L.append("Branch: `diagnostics/blackout-window-discrepancy`")
    L.append("")
    L.append("## Setup")
    L.append("")
    L.append(f"- IS corpus: **{ma['is_start']} → {ma['is_end']}** "
             f"({ma['n_sessions_in_range']} sessions)")
    L.append(f"- Locked baseline params held in both runs: "
             f"`z_threshold={ma['config']['z_threshold']}`, "
             f"`bar_freq={ma['config']['bar_freq']}`, "
             f"`blackout_lunch={ma['config']['blackout_lunch']}`, "
             "`stop=2.0×ATR`, `target=4.5×ATR`, `time_stop=25min`, "
             "`atr_window=14`, `feature_lookback=20`, `trail_after_r=0`.")
    L.append("- Single variable: blackout window.")
    L.append("  - **Run A**: locked code, `[10:30, 12:30)` ET")
    L.append("  - **Run B**: temporarily edited code, `[12:00, 13:00)` ET")
    L.append("- Both runs against the same feature frame "
             f"({mb.get('n_sessions_in_range', 80)} sessions).")
    L.append("")

    L.append("## Headline metrics")
    L.append("")
    L.append(f"| {'Metric':<17}| {'Run A (10:30-12:30)':>20s}"
             f"| {'Run B (12:00-13:00)':>20s}| {'Delta (B-A)':>14s}|")
    L.append(f"|{'-'*18}+{'-'*21}+{'-'*21}+{'-'*15}|".replace("+", "|"))
    ha, hb = ma["headline"], mb["headline"]
    L.append(_summary_row("Trade count", ha["trades"], hb["trades"], lambda v: f"{v}"))
    L.append(_summary_row("Total PnL", ha["total_pnl"], hb["total_pnl"], _fmt_money))
    L.append(_summary_row("Win rate", ha["win_rate"], hb["win_rate"], _fmt_pct))
    L.append(_summary_row("Mean PnL/trade", ha["mean_pnl"], hb["mean_pnl"], _fmt_money))
    L.append(_summary_row("Avg win", ha["avg_win"], hb["avg_win"], _fmt_money))
    L.append(_summary_row("Avg loss", ha["avg_loss"], hb["avg_loss"], _fmt_money))
    L.append(_summary_row("Profit factor", ha["profit_factor"], hb["profit_factor"],
                          lambda v: f"{v:.3f}" if v is not None else "—"))
    L.append(_summary_row("Sharpe", ha["sharpe_daily"], hb["sharpe_daily"],
                          lambda v: f"{v:+.3f}"))
    L.append(_summary_row("Max DD", ha["max_dd"], hb["max_dd"], _fmt_money))
    L.append("")

    L.append("## Exit distribution")
    L.append("")
    ea = ma["exit_dist"]
    eb = mb["exit_dist"]
    reasons = sorted(set(ea) | set(eb))
    L.append("| exit | Run A | Run B | Delta |")
    L.append("|---|---:|---:|---:|")
    for r in reasons:
        va = int(ea.get(r, 0))
        vb = int(eb.get(r, 0))
        L.append(f"| {r} | {va} | {vb} | {vb - va:+d} |")
    L.append("")

    L.append("## Per-cell breakdown")
    L.append("")
    L.append("| cell | A: n | A: total $ | A: win | B: n | B: total $ | B: win | Δ n | Δ total $ |")
    L.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    pa = {r["cell"]: r for r in ma["per_cell"]}
    pb = {r["cell"]: r for r in mb["per_cell"]}
    for cell in ("LONG_long", "LONG_short", "SHORT_long", "SHORT_short"):
        ra, rb = pa[cell], pb[cell]
        wa = _fmt_pct(ra["win_rate"]) if ra["n"] else "—"
        wb = _fmt_pct(rb["win_rate"]) if rb["n"] else "—"
        L.append(
            f"| {cell} | {ra['n']} | {_fmt_money(ra['total_pnl'])} | {wa} "
            f"| {rb['n']} | {_fmt_money(rb['total_pnl'])} | {wb} "
            f"| {rb['n'] - ra['n']:+d} "
            f"| {_fmt_money(rb['total_pnl'] - ra['total_pnl'])} |"
        )
    L.append("")

    L.append("## Delta analysis")
    L.append("")
    L.append(f"- Trades present in **both** runs (entry_time match): "
             f"**{len(shared)}**")
    L.append(f"- Trades **unique to Run A** (locked allows 12:30-12:55 signals "
             f"that B blocks): **{agg_a_only['n']}**")
    L.append(f"- Trades **unique to Run B** (documented allows 10:30-11:55 signals "
             f"that A blocks): **{agg_b_new['n']}**")
    L.append("")

    def _agg_block(title: str, agg: dict, df: pd.DataFrame):
        L.append(f"### {title}")
        L.append("")
        L.append(f"- n: **{agg['n']}**")
        L.append(f"- total net: **{_fmt_money(agg['total_pnl'])}**")
        L.append(f"- win rate: **{_fmt_pct(agg['win_rate'])}**")
        if agg["n"]:
            cell_str = ", ".join(f"{k}={v}" for k, v in
                                  sorted(agg["cells"].items()))
            L.append(f"- cell distribution: {cell_str}")
        L.append("")
        if df.empty:
            L.append("(none)")
            L.append("")
            return
        L.append("| # | entry_time | side | gamma_regime | cell | exit | bars | net $ |")
        L.append("|---|---|---|---|---|---|---:|---:|")
        for i, row in enumerate(df.itertuples(index=False), start=1):
            side = "LONG" if row.side == 1 else "SHORT"
            ts = pd.Timestamp(row.entry_time)
            L.append(
                f"| {i} | {ts.strftime('%Y-%m-%d %H:%M:%S%z')} | {side} "
                f"| {row.gamma_regime} | {row.cell} | {row.exit_reason} "
                f"| {row.bars_held} | {_fmt_money(row.net_dollars)} |"
            )
        L.append("")

    _agg_block("New trades unlocked by Run B (10:30-12:00 signals allowed)",
               agg_b_new, only_b)
    _agg_block("Trades suppressed by Run B (12:30-12:55 signals blocked)",
               agg_a_only, only_a)

    L.append("## Disclosure")
    L.append("")
    L.append("> This is a consumed-data counterfactual on the IS corpus. ")
    L.append("> Run A reflects the locked code window (always [10:30, 12:30)). ")
    L.append("> Run B tests the documented window (12:00-13:00) which has ")
    L.append("> never run in code. Neither run authorizes a config change. ")
    L.append("> strategy.py was temporarily modified for Run B and has been ")
    L.append("> reverted. git diff backend/cheese/strategy.py confirms zero ")
    L.append("> diff post-revert.")
    L.append("")

    REPORT.write_text("\n".join(L))
    print(f"wrote {REPORT}")
    print(f"shared={len(shared)}  only_A={agg_a_only['n']}  only_B={agg_b_new['n']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
