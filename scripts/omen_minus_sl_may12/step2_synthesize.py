"""Synthesis for the 9-session OMEN-minus-SL pulse (May 12 included)."""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

REPO = Path("/Users/rafanelson/Omen")
ANALYSIS = REPO / "analysis/omen-minus-sl-may12-pulse"
ET = ZoneInfo("America/New_York")

FRESH_CSV = ANALYSIS / "fresh_trades_9sessions.csv"
MINUS_CSV = ANALYSIS / "fresh_trades_minus_sl.csv"
OUT_MD = ANALYSIS / "SYNTHESIS.md"

SL_CELL = "SHORT_long"
CELLS = ["LONG_long", "LONG_short", "SHORT_long", "SHORT_short"]

# 8-session bugfixed comparison (from analysis/omen-minus-sl-bugfixed/SYNTHESIS.md)
PRIOR_8SESSION = {
    "n_sessions": 8, "n_full": 24, "n_minus": 22,
    "full_sharpe": +1.28, "full_sum": +349, "full_win": 0.625, "full_mean": +14.53,
    "minus_sharpe": +2.66, "minus_sum": +690, "minus_win": 0.636, "minus_mean": +31.36,
    "sl_n": 2, "sl_sum": -341, "sl_mean": -170.62,
    "cells": {"LONG_long": 3, "LONG_short": 9, "SHORT_long": 2, "SHORT_short": 10},
}

DISCLOSURE = """\
## DISCLOSURE — partially-consumed pool, pulse only

These 9 fresh sessions have been used for multiple prior analyses
(original quick-check, ATR=20 variant, Zach May params, bugfixed
re-run). Adding May 12 is a 9th-session extension of an already-
consumed pool. Cumulatively biased.

Sample size remains far too small for any verdict. The locked
pre-registered forward test (commit `9c1c22f`) requires 30+ fresh
sessions and has not yet been triggered.
"""


def _load(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["entry_time"] = pd.to_datetime(df["entry_time"], utc=True)
    df["entry_time_utc"] = df["entry_time"]
    df["entry_time_et"] = df["entry_time"].dt.tz_convert(ET)
    df["exit_time"] = pd.to_datetime(df["exit_time"], utc=True)
    df["exit_time_et"] = df["exit_time"].dt.tz_convert(ET)
    df["entry_date"] = df["entry_time_et"].dt.date
    df["side_label"] = np.where(df["side"] == 1, "LONG", "SHORT")
    df["cell"] = df["side_label"] + "_" + df["gamma_regime"].astype(str)
    return df


def _max_dd(net, t):
    if len(net) == 0:
        return 0.0
    order = t.argsort()
    eq = np.cumsum(net.values[order])
    return float((eq - np.maximum.accumulate(eq)).min())


def _sharpe(net, n_sessions, min_n=10):
    n = len(net)
    if n < min_n or n_sessions <= 0:
        return None
    tpd = n / n_sessions
    m = float(net.mean()); s = float(net.std(ddof=1))
    if s == 0:
        return None
    return ((m * tpd) / (s * np.sqrt(tpd))) * np.sqrt(252)


def _stats(df, n_sessions):
    if len(df) == 0:
        return {"n": 0, "win_rate": None, "mean": 0.0, "sum": 0.0,
                "sharpe": None, "max_dd": 0.0}
    net = df["net_dollars"]
    return {"n": int(len(df)), "win_rate": float((net > 0).mean()),
             "mean": float(net.mean()), "sum": float(net.sum()),
             "sharpe": _sharpe(net, n_sessions),
             "max_dd": _max_dd(net, df["entry_time_utc"])}


def _fmt_sh(sh): return "—" if sh is None else f"{sh:+.2f}"
def _fmt_wr(wr): return "—" if wr is None else f"{wr*100:.1f}%"


def main() -> int:
    trades = _load(FRESH_CSV)
    n_sessions = trades["entry_date"].nunique()
    dates = sorted(trades["entry_date"].unique())

    full = trades.copy()
    minus = trades[trades["cell"] != SL_CELL].copy()
    minus.to_csv(MINUS_CSV, index=False)

    full_st = _stats(full, n_sessions)
    minus_st = _stats(minus, n_sessions)
    per_cell = {c: _stats(trades[trades["cell"] == c], n_sessions) for c in CELLS}
    exits = trades["exit_reason"].value_counts().to_dict()

    import datetime as dt
    may12 = full[full["entry_date"] == dt.date(2026, 5, 12)]

    print(f"9-session pulse: full n={full_st['n']}, minus-SL n={minus_st['n']}")
    print(f"  full Sharpe={_fmt_sh(full_st['sharpe'])}  "
          f"minus-SL Sharpe={_fmt_sh(minus_st['sharpe'])}")
    print(f"  May 12: n={len(may12)}, net=${may12['net_dollars'].sum():+.2f}")

    L: list[str] = []
    L.append("# OMEN-minus-SL 9-session pulse (May 12 included) — THROWAWAY\n")
    L.append("Branch: `analysis/omen-minus-sl-may12-pulse-throwaway` "
             "(throwaway / archive only; never merges to main).")
    L.append(f"Generated: {datetime.now().isoformat(timespec='seconds')}\n")
    L.append("## 1. Disclosure\n")
    L.append(DISCLOSURE)
    L.append("")
    L.append("## 2. Setup\n")
    L.append(f"- Fresh sessions: **{n_sessions}** "
             f"({dates[0].isoformat()} → {dates[-1].isoformat()}).")
    L.append("- Bugfixed infrastructure on main (features.py session-boundary fix + "
             "backtest.py time-stop + overlap fixes).")
    L.append("- Locked baseline params unchanged: z=1.8, blackout_lunch=True, "
             "stop=2.0×ATR, target=4.5×ATR, time_stop=25min, ATR=14, bar_freq=5min.")
    L.append("- ES 1s sources: 3 parquet files concatenated in-memory "
             "(primary 9/8→4/27, data-refresh 4/28→5/11, May 12 single-day pull).")
    L.append("")

    L.append("## 3. 9-session metrics\n")
    L.append("| arm | N | win | mean $ | sum $ | Sharpe | max DD |")
    L.append("|---|---:|---:|---:|---:|---:|---:|")
    for label, st in (("full_omen_bugfixed", full_st),
                       ("omen_minus_sl_bugfixed", minus_st)):
        L.append(f"| {label} | {st['n']} | {_fmt_wr(st['win_rate'])} | "
                 f"${st['mean']:+.2f} | ${st['sum']:+.0f} | "
                 f"{_fmt_sh(st['sharpe'])} | ${st['max_dd']:+.0f} |")
    L.append("")
    L.append("### Per-cell breakdown\n")
    L.append("| cell | N | mean $ | sum $ | Sharpe (if N≥10) |")
    L.append("|---|---:|---:|---:|---:|")
    for c in CELLS:
        s = per_cell[c]
        sh_str = _fmt_sh(s["sharpe"]) if s["n"] >= 10 else f"(n<10: n={s['n']})"
        L.append(f"| {c} | {s['n']} | ${s['mean']:+.2f} | ${s['sum']:+.0f} | {sh_str} |")
    L.append("")
    L.append("### Exit-reason distribution\n")
    L.append("| exit_reason | count |")
    L.append("|---|---:|")
    for r in ("time", "stop", "target", "trail", "session_close"):
        L.append(f"| {r} | {exits.get(r, 0)} |")
    L.append("")

    L.append("## 4. Comparison: 8-session bugfixed vs 9-session (this pulse)\n")
    L.append("| metric | 8-session (bugfixed) | 9-session (this) | Δ |")
    L.append("|---|---:|---:|---:|")
    L.append(f"| Full OMEN N | {PRIOR_8SESSION['n_full']} | {full_st['n']} | "
             f"{full_st['n'] - PRIOR_8SESSION['n_full']:+d} |")
    L.append(f"| Full OMEN win rate | {PRIOR_8SESSION['full_win']*100:.1f}% | "
             f"{_fmt_wr(full_st['win_rate'])} | "
             f"{(full_st['win_rate']-PRIOR_8SESSION['full_win'])*100:+.1f} pp |")
    L.append(f"| Full OMEN mean $ | ${PRIOR_8SESSION['full_mean']:+.2f} | "
             f"${full_st['mean']:+.2f} | "
             f"${full_st['mean']-PRIOR_8SESSION['full_mean']:+.2f} |")
    L.append(f"| Full OMEN sum $ | ${PRIOR_8SESSION['full_sum']:+.0f} | "
             f"${full_st['sum']:+.0f} | "
             f"${full_st['sum']-PRIOR_8SESSION['full_sum']:+.0f} |")
    L.append(f"| **Full OMEN Sharpe** | **{PRIOR_8SESSION['full_sharpe']:+.2f}** | "
             f"**{_fmt_sh(full_st['sharpe'])}** | "
             f"**{(full_st['sharpe'] or 0)-PRIOR_8SESSION['full_sharpe']:+.2f}** |")
    L.append(f"| Minus-SL N | {PRIOR_8SESSION['n_minus']} | {minus_st['n']} | "
             f"{minus_st['n'] - PRIOR_8SESSION['n_minus']:+d} |")
    L.append(f"| Minus-SL mean $ | ${PRIOR_8SESSION['minus_mean']:+.2f} | "
             f"${minus_st['mean']:+.2f} | "
             f"${minus_st['mean']-PRIOR_8SESSION['minus_mean']:+.2f} |")
    L.append(f"| Minus-SL sum $ | ${PRIOR_8SESSION['minus_sum']:+.0f} | "
             f"${minus_st['sum']:+.0f} | "
             f"${minus_st['sum']-PRIOR_8SESSION['minus_sum']:+.0f} |")
    L.append(f"| **Minus-SL Sharpe** | **{PRIOR_8SESSION['minus_sharpe']:+.2f}** | "
             f"**{_fmt_sh(minus_st['sharpe'])}** | "
             f"**{(minus_st['sharpe'] or 0)-PRIOR_8SESSION['minus_sharpe']:+.2f}** |")
    L.append(f"| SHORT_long N | {PRIOR_8SESSION['sl_n']} | "
             f"{per_cell[SL_CELL]['n']} | "
             f"{per_cell[SL_CELL]['n']-PRIOR_8SESSION['sl_n']:+d} |")
    L.append(f"| SHORT_long sum $ | ${PRIOR_8SESSION['sl_sum']:+.0f} | "
             f"${per_cell[SL_CELL]['sum']:+.0f} | "
             f"${per_cell[SL_CELL]['sum']-PRIOR_8SESSION['sl_sum']:+.0f} |")
    L.append("")

    L.append("## 5. May 12 trade detail\n")
    if len(may12) == 0:
        L.append("No trades on May 12.")
    else:
        L.append(f"May 12 contributed **{len(may12)} trade(s)**, total net = "
                 f"**${may12['net_dollars'].sum():+.2f}**.")
        L.append("")
        L.append("| entry_time ET | side | gamma_regime | entry $ | exit $ | "
                 "exit_reason | bars held | net $ |")
        L.append("|---|---|---|---:|---:|---|---:|---:|")
        for _, r in may12.iterrows():
            side = "LONG" if r["side"] == 1 else "SHORT"
            bars = int(r["bars_held"]) if pd.notna(r.get("bars_held")) else "—"
            L.append(f"| {r['entry_time_et'].strftime('%H:%M')} | {side} | "
                     f"{r['gamma_regime']} | "
                     f"${r['entry_px']:.2f} | ${r['exit_px']:.2f} | "
                     f"{r['exit_reason']} | {bars} | ${r['net_dollars']:+.2f} |")
        L.append("")
        # Which cells did May 12 contribute to?
        may12_cells = may12["cell"].value_counts().to_dict()
        L.append(f"May 12 cells: " + ", ".join(f"{c}×{n}" for c, n in may12_cells.items()) + ".")
    L.append("")

    L.append("## 6. Per-session pulse table\n")
    L.append("| session | N trades | net $ |")
    L.append("|---|---:|---:|")
    for d in dates:
        sub = trades[trades["entry_date"] == d]
        L.append(f"| {d.isoformat()} | {len(sub)} | ${sub['net_dollars'].sum():+.2f} |")
    L.append(f"| **TOTAL** | **{len(trades)}** | **${trades['net_dollars'].sum():+.2f}** |")
    L.append("")

    L.append("## 7. Honest note\n")
    L.append(f"This is **a pulse, not validation**. The 9-session sample is the "
             "5th analysis touching this fresh-session pool (original quick-check, ")
    L.append("ATR=20 variant, Zach May, bugfixed re-run, this May-12 extension). The data is ")
    L.append("cumulatively biased.")
    L.append("")
    L.append("The pre-registered forward test (`9c1c22f`) requires **≥ 30 fresh sessions** ")
    L.append(f"for a verdict on the OMEN-minus-SL hypothesis. Current accumulated session ")
    L.append(f"count is **{n_sessions} / 30** (30% of the required minimum).")
    L.append("")
    L.append("Pulse readings (e.g., minus-SL Sharpe > full Sharpe persisting from 8 to 9 ")
    L.append("sessions) are **directionally interesting** but cannot establish the ")
    L.append("hypothesis. The pulse continues, the pre-reg holds.")
    L.append("")

    OUT_MD.write_text("\n".join(L) + "\n")
    print(f"\nSaved synthesis: {OUT_MD}")
    print(f"Saved minus-SL csv: {MINUS_CSV}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
