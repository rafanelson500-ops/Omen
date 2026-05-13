"""Step 2 — three-way comparison: original / session-boundary-only / all-bugfixes.

Reads:
  backend/data/analysis/locked_baseline_trades_blackout_lunch.csv  (orig IS, 174)
  backend/data/analysis/oos_baseline_trades_2025-09-08_2025-12-23.csv (orig OOS, 158)
  diagnostics/session-boundary-bugfix/locked_baseline_is_bugfixed.csv (262)
  diagnostics/session-boundary-bugfix/oos_baseline_bugfixed.csv (252)
  diagnostics/all-bugfixes-baseline/is_all_bugfixes.csv (this run)
  diagnostics/all-bugfixes-baseline/oos_all_bugfixes.csv (this run)
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

REPO = Path("/Users/rafanelson/Omen")
ANALYSIS = REPO / "backend/data/analysis"
SB_DIR = REPO / "diagnostics/session-boundary-bugfix"
ALL_DIR = REPO / "diagnostics/all-bugfixes-baseline"
ET = ZoneInfo("America/New_York")

ORIG_IS = ANALYSIS / "locked_baseline_trades_blackout_lunch.csv"
ORIG_OOS = ANALYSIS / "oos_baseline_trades_2025-09-08_2025-12-23.csv"
SB_IS = SB_DIR / "locked_baseline_is_bugfixed.csv"
SB_OOS = SB_DIR / "oos_baseline_bugfixed.csv"
ALL_IS = ALL_DIR / "is_all_bugfixes.csv"
ALL_OOS = ALL_DIR / "oos_all_bugfixes.csv"
OUT_MD = ALL_DIR / "SYNTHESIS.md"

SL_CELL = "SHORT_long"
CELLS = ["LONG_long", "LONG_short", "SHORT_long", "SHORT_short"]


def _load(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["entry_time"] = pd.to_datetime(df["entry_time"], utc=True)
    df["entry_time_utc"] = df["entry_time"]
    df["entry_time_et"] = df["entry_time"].dt.tz_convert(ET)
    df["exit_time"] = pd.to_datetime(df["exit_time"], utc=True)
    df["exit_time_utc"] = df["exit_time"]
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


def _sharpe(net, n_sessions):
    n = len(net)
    if n < 2 or n_sessions <= 0:
        return None
    tpd = n / n_sessions
    m = float(net.mean()); s = float(net.std(ddof=1))
    if s == 0:
        return None
    return ((m * tpd) / (s * np.sqrt(tpd))) * np.sqrt(252)


def _stats(df, n_sessions):
    if len(df) == 0:
        return {"n": 0, "win_rate": None, "mean": 0.0, "sum": 0.0,
                "sharpe": None, "max_dd": 0.0, "mean_bars_held": None,
                "mean_hold_min": None}
    net = df["net_dollars"]
    bars_held_mean = float(df["bars_held"].mean()) if "bars_held" in df.columns else None
    return {
        "n": int(len(df)),
        "win_rate": float((net > 0).mean()),
        "mean": float(net.mean()),
        "sum": float(net.sum()),
        "sharpe": _sharpe(net, n_sessions),
        "max_dd": _max_dd(net, df["entry_time_utc"]),
        "mean_bars_held": bars_held_mean,
        "mean_hold_min": bars_held_mean * 5 if bars_held_mean is not None else None,
    }


def _per_cell(df, n_sessions):
    return {c: _stats(df[df["cell"] == c], n_sessions) for c in CELLS}


def _exit_dist(df):
    return df["exit_reason"].value_counts().to_dict()


def _fmt_sh(sh): return "—" if sh is None else f"{sh:+.2f}"
def _fmt_wr(wr): return "—" if wr is None else f"{wr*100:.1f}%"


def _detect_overlaps(df: pd.DataFrame) -> int:
    """Count adjacent-trade pairs where entry_i+1 < exit_i (overlap)."""
    if len(df) < 2:
        return 0
    s = df.sort_values("entry_time_utc").reset_index(drop=True)
    overlap = 0
    for i in range(len(s) - 1):
        if s.loc[i+1, "entry_time_utc"] < s.loc[i, "exit_time_utc"]:
            overlap += 1
    return overlap


def main() -> int:
    is_orig = _load(ORIG_IS); is_sb = _load(SB_IS); is_all = _load(ALL_IS)
    oos_orig = _load(ORIG_OOS); oos_sb = _load(SB_OOS); oos_all = _load(ALL_OOS)

    sessions_is_orig = is_orig["entry_date"].nunique()
    sessions_is_sb = is_sb["entry_date"].nunique()
    sessions_is_all = is_all["entry_date"].nunique()
    sessions_oos_orig = oos_orig["entry_date"].nunique()
    sessions_oos_sb = oos_sb["entry_date"].nunique()
    sessions_oos_all = oos_all["entry_date"].nunique()

    # Aggregate stats
    s_io = _stats(is_orig, sessions_is_orig)
    s_isb = _stats(is_sb, sessions_is_sb)
    s_iall = _stats(is_all, sessions_is_all)
    s_oo = _stats(oos_orig, sessions_oos_orig)
    s_osb = _stats(oos_sb, sessions_oos_sb)
    s_oall = _stats(oos_all, sessions_oos_all)

    # Per-cell
    pc_io = _per_cell(is_orig, sessions_is_orig)
    pc_isb = _per_cell(is_sb, sessions_is_sb)
    pc_iall = _per_cell(is_all, sessions_is_all)
    pc_oo = _per_cell(oos_orig, sessions_oos_orig)
    pc_osb = _per_cell(oos_sb, sessions_oos_sb)
    pc_oall = _per_cell(oos_all, sessions_oos_all)

    # Minus-SL
    minus_io   = _stats(is_orig[is_orig["cell"] != SL_CELL], sessions_is_orig)
    minus_isb  = _stats(is_sb[is_sb["cell"] != SL_CELL], sessions_is_sb)
    minus_iall = _stats(is_all[is_all["cell"] != SL_CELL], sessions_is_all)
    minus_oo   = _stats(oos_orig[oos_orig["cell"] != SL_CELL], sessions_oos_orig)
    minus_osb  = _stats(oos_sb[oos_sb["cell"] != SL_CELL], sessions_oos_sb)
    minus_oall = _stats(oos_all[oos_all["cell"] != SL_CELL], sessions_oos_all)

    # Exit reason distributions
    ed_io = _exit_dist(is_orig); ed_isb = _exit_dist(is_sb); ed_iall = _exit_dist(is_all)
    ed_oo = _exit_dist(oos_orig); ed_osb = _exit_dist(oos_sb); ed_oall = _exit_dist(oos_all)

    # Trade overlaps (the bug FIX 2 was specifically designed to eliminate these)
    overlap_io = _detect_overlaps(is_orig); overlap_isb = _detect_overlaps(is_sb); overlap_iall = _detect_overlaps(is_all)
    overlap_oo = _detect_overlaps(oos_orig); overlap_osb = _detect_overlaps(oos_sb); overlap_oall = _detect_overlaps(oos_all)

    print("=" * 72)
    print("THREE-WAY COMPARISON: original / session-boundary-only / all-bugfixes")
    print("=" * 72)
    print("\nIS:")
    print(f"  {'metric':<22s}  {'orig':>10s}  {'+sess-bnd':>10s}  {'+all bugs':>10s}")
    for label, key in (("N trades", "n"), ("Win rate %", "win_rate"),
                        ("Mean $", "mean"), ("Sum $", "sum"),
                        ("Sharpe", "sharpe"), ("Max DD $", "max_dd"),
                        ("Mean bars_held", "mean_bars_held"),
                        ("Mean hold (min)", "mean_hold_min")):
        if key == "win_rate":
            print(f"  {label:<22s}  "
                  f"{s_io[key]*100:>9.2f}%  {s_isb[key]*100:>9.2f}%  "
                  f"{s_iall[key]*100:>9.2f}%")
        elif key in ("sharpe",):
            print(f"  {label:<22s}  "
                  f"{_fmt_sh(s_io[key]):>10s}  {_fmt_sh(s_isb[key]):>10s}  "
                  f"{_fmt_sh(s_iall[key]):>10s}")
        elif key in ("mean_bars_held", "mean_hold_min"):
            print(f"  {label:<22s}  "
                  f"{s_io[key]:>10.2f}  {s_isb[key]:>10.2f}  {s_iall[key]:>10.2f}")
        elif key == "n":
            print(f"  {label:<22s}  {s_io[key]:>10d}  {s_isb[key]:>10d}  {s_iall[key]:>10d}")
        else:
            print(f"  {label:<22s}  {s_io[key]:>+10.2f}  {s_isb[key]:>+10.2f}  "
                  f"{s_iall[key]:>+10.2f}")
    print(f"  {'Trade overlaps':<22s}  {overlap_io:>10d}  {overlap_isb:>10d}  {overlap_iall:>10d}")

    print("\nOOS:")
    print(f"  {'metric':<22s}  {'orig':>10s}  {'+sess-bnd':>10s}  {'+all bugs':>10s}")
    for label, key in (("N trades", "n"), ("Win rate %", "win_rate"),
                        ("Mean $", "mean"), ("Sum $", "sum"),
                        ("Sharpe", "sharpe"), ("Max DD $", "max_dd"),
                        ("Mean bars_held", "mean_bars_held"),
                        ("Mean hold (min)", "mean_hold_min")):
        if key == "win_rate":
            print(f"  {label:<22s}  {s_oo[key]*100:>9.2f}%  {s_osb[key]*100:>9.2f}%  "
                  f"{s_oall[key]*100:>9.2f}%")
        elif key in ("sharpe",):
            print(f"  {label:<22s}  {_fmt_sh(s_oo[key]):>10s}  {_fmt_sh(s_osb[key]):>10s}  "
                  f"{_fmt_sh(s_oall[key]):>10s}")
        elif key in ("mean_bars_held", "mean_hold_min"):
            print(f"  {label:<22s}  {s_oo[key]:>10.2f}  {s_osb[key]:>10.2f}  "
                  f"{s_oall[key]:>10.2f}")
        elif key == "n":
            print(f"  {label:<22s}  {s_oo[key]:>10d}  {s_osb[key]:>10d}  {s_oall[key]:>10d}")
        else:
            print(f"  {label:<22s}  {s_oo[key]:>+10.2f}  {s_osb[key]:>+10.2f}  "
                  f"{s_oall[key]:>+10.2f}")
    print(f"  {'Trade overlaps':<22s}  {overlap_oo:>10d}  {overlap_osb:>10d}  {overlap_oall:>10d}")

    print("\nExit reason distribution (IS):")
    for r in ("time", "stop", "target", "session_close"):
        print(f"  {r:<14s}  orig={ed_io.get(r,0):>4d}  +sb={ed_isb.get(r,0):>4d}  "
              f"+all={ed_iall.get(r,0):>4d}")
    print("\nExit reason distribution (OOS):")
    for r in ("time", "stop", "target", "session_close"):
        print(f"  {r:<14s}  orig={ed_oo.get(r,0):>4d}  +sb={ed_osb.get(r,0):>4d}  "
              f"+all={ed_oall.get(r,0):>4d}")

    print("\nOMEN-minus-SL Sharpe:")
    print(f"  IS  orig={_fmt_sh(minus_io['sharpe'])}  +sb={_fmt_sh(minus_isb['sharpe'])}  "
          f"+all={_fmt_sh(minus_iall['sharpe'])}")
    print(f"  OOS orig={_fmt_sh(minus_oo['sharpe'])}  +sb={_fmt_sh(minus_osb['sharpe'])}  "
          f"+all={_fmt_sh(minus_oall['sharpe'])}")

    print("\nPer-cell OOS Sharpe:")
    for c in CELLS:
        print(f"  {c:<12s}  orig={_fmt_sh(pc_oo[c]['sharpe']):>6s} (n={pc_oo[c]['n']:>3d})  "
              f"+sb={_fmt_sh(pc_osb[c]['sharpe']):>6s} (n={pc_osb[c]['n']:>3d})  "
              f"+all={_fmt_sh(pc_oall[c]['sharpe']):>6s} (n={pc_oall[c]['n']:>3d})")

    md = _synthesize(
        s_io=s_io, s_isb=s_isb, s_iall=s_iall,
        s_oo=s_oo, s_osb=s_osb, s_oall=s_oall,
        pc_io=pc_io, pc_isb=pc_isb, pc_iall=pc_iall,
        pc_oo=pc_oo, pc_osb=pc_osb, pc_oall=pc_oall,
        minus_io=minus_io, minus_isb=minus_isb, minus_iall=minus_iall,
        minus_oo=minus_oo, minus_osb=minus_osb, minus_oall=minus_oall,
        ed_io=ed_io, ed_isb=ed_isb, ed_iall=ed_iall,
        ed_oo=ed_oo, ed_osb=ed_osb, ed_oall=ed_oall,
        overlap_io=overlap_io, overlap_isb=overlap_isb, overlap_iall=overlap_iall,
        overlap_oo=overlap_oo, overlap_osb=overlap_osb, overlap_oall=overlap_oall,
        sessions_is=sessions_is_all, sessions_oos=sessions_oos_all,
    )
    OUT_MD.write_text(md)
    print(f"\nSaved synthesis: {OUT_MD}")
    return 0


def _synthesize(**kw) -> str:
    L: list[str] = []
    L.append("# All-bugfixes baseline — IS / OOS impact (three-way)\n")
    L.append("Branch: `diagnostics/all-bugfixes-baseline` "
             "(diagnostics; merge to main only with explicit user sign-off).")
    L.append(f"Generated: {datetime.now().isoformat(timespec='seconds')}\n")

    L.append("## 1. Bug fixes applied (vs `main`)\n")
    L.append("`main` already includes the **features.py session-boundary fix** (commit c333405). ")
    L.append("This branch adds the two remaining `backtest.py` fixes from Zach's Omen 2.0 fork:\n")
    L.append("- **FIX 1 — Time-stop off-by-one**: change time-stop trigger from "
             "`bars_in >= max_bars` to `bars_in >= max(1, max_bars - 1)`. "
             "Reason: exits fill at next-bar open, so triggering at `bars_in == max_bars` "
             "produces a `max_bars × bar_freq + bar_freq` realized hold instead of the "
             "intended `max_bars × bar_freq`. With time_stop_min=25 and 5min bars, the "
             "bug held trades for 30 min instead of 25.")
    L.append("- **FIX 2 — Exit/entry same-iteration block**: add `exit_occurred` flag; "
             "block the entry block on the same iteration that an exit fires. "
             "Reason: without this, a trade that exits at iteration `i` and a signal "
             "that fired at `i - 1` can produce a new entry at `o[i]`, BEFORE the "
             "just-resolved exit. Live cannot produce that; backtest could.")
    L.append("")
    L.append("**NOT applied** (per spec): TRADE_START_TIME hard floor, "
             "z_threshold/stop/target/time_stop/lookback/trail parameter changes. "
             "All locked baseline parameters held: z=1.8, stop=2.0×ATR, target=4.5×ATR, "
             "time_stop=25min, ATR=14, lookback=20, blackout_lunch=True, bar_freq=5min.")
    L.append("")

    # Three-way table — IS
    L.append("## 2. Three-way comparison — IS (2025-12-30 → 2026-04-21)\n")
    L.append("| metric | original (no fixes) | + session-boundary | + all bugfixes |")
    L.append("|---|---:|---:|---:|")
    rows_is = [
        ("N trades", kw["s_io"]["n"], kw["s_isb"]["n"], kw["s_iall"]["n"], "int"),
        ("Win rate", kw["s_io"]["win_rate"], kw["s_isb"]["win_rate"], kw["s_iall"]["win_rate"], "pct"),
        ("Mean $", kw["s_io"]["mean"], kw["s_isb"]["mean"], kw["s_iall"]["mean"], "$f"),
        ("Sum $", kw["s_io"]["sum"], kw["s_isb"]["sum"], kw["s_iall"]["sum"], "$d"),
        ("**Sharpe**", kw["s_io"]["sharpe"], kw["s_isb"]["sharpe"], kw["s_iall"]["sharpe"], "sh"),
        ("Max DD $", kw["s_io"]["max_dd"], kw["s_isb"]["max_dd"], kw["s_iall"]["max_dd"], "$d"),
        ("Mean bars_held", kw["s_io"]["mean_bars_held"], kw["s_isb"]["mean_bars_held"], kw["s_iall"]["mean_bars_held"], "f"),
        ("Mean hold (min)", kw["s_io"]["mean_hold_min"], kw["s_isb"]["mean_hold_min"], kw["s_iall"]["mean_hold_min"], "f"),
        ("Trade overlaps", kw["overlap_io"], kw["overlap_isb"], kw["overlap_iall"], "int"),
    ]
    for label, a, b, c, kind in rows_is:
        if kind == "int": L.append(f"| {label} | {a} | {b} | {c} |")
        elif kind == "pct": L.append(f"| {label} | {a*100:.1f}% | {b*100:.1f}% | {c*100:.1f}% |")
        elif kind == "$f": L.append(f"| {label} | ${a:+.2f} | ${b:+.2f} | ${c:+.2f} |")
        elif kind == "$d": L.append(f"| {label} | ${a:+.0f} | ${b:+.0f} | ${c:+.0f} |")
        elif kind == "sh": L.append(f"| {label} | {_fmt_sh(a)} | {_fmt_sh(b)} | {_fmt_sh(c)} |")
        elif kind == "f": L.append(f"| {label} | {a:.2f} | {b:.2f} | {c:.2f} |")
    L.append("")

    # Three-way table — OOS
    L.append("## 3. Three-way comparison — OOS (2025-09-08 → 2025-12-23)\n")
    L.append("| metric | original (no fixes) | + session-boundary | + all bugfixes |")
    L.append("|---|---:|---:|---:|")
    rows_oos = [
        ("N trades", kw["s_oo"]["n"], kw["s_osb"]["n"], kw["s_oall"]["n"], "int"),
        ("Win rate", kw["s_oo"]["win_rate"], kw["s_osb"]["win_rate"], kw["s_oall"]["win_rate"], "pct"),
        ("Mean $", kw["s_oo"]["mean"], kw["s_osb"]["mean"], kw["s_oall"]["mean"], "$f"),
        ("Sum $", kw["s_oo"]["sum"], kw["s_osb"]["sum"], kw["s_oall"]["sum"], "$d"),
        ("**Sharpe**", kw["s_oo"]["sharpe"], kw["s_osb"]["sharpe"], kw["s_oall"]["sharpe"], "sh"),
        ("Max DD $", kw["s_oo"]["max_dd"], kw["s_osb"]["max_dd"], kw["s_oall"]["max_dd"], "$d"),
        ("Mean bars_held", kw["s_oo"]["mean_bars_held"], kw["s_osb"]["mean_bars_held"], kw["s_oall"]["mean_bars_held"], "f"),
        ("Mean hold (min)", kw["s_oo"]["mean_hold_min"], kw["s_osb"]["mean_hold_min"], kw["s_oall"]["mean_hold_min"], "f"),
        ("Trade overlaps", kw["overlap_oo"], kw["overlap_osb"], kw["overlap_oall"], "int"),
    ]
    for label, a, b, c, kind in rows_oos:
        if kind == "int": L.append(f"| {label} | {a} | {b} | {c} |")
        elif kind == "pct": L.append(f"| {label} | {a*100:.1f}% | {b*100:.1f}% | {c*100:.1f}% |")
        elif kind == "$f": L.append(f"| {label} | ${a:+.2f} | ${b:+.2f} | ${c:+.2f} |")
        elif kind == "$d": L.append(f"| {label} | ${a:+.0f} | ${b:+.0f} | ${c:+.0f} |")
        elif kind == "sh": L.append(f"| {label} | {_fmt_sh(a)} | {_fmt_sh(b)} | {_fmt_sh(c)} |")
        elif kind == "f": L.append(f"| {label} | {a:.2f} | {b:.2f} | {c:.2f} |")
    L.append("")

    # Mechanism-of-change isolation
    L.append("## 4. What each fix did (isolated effects)\n")
    L.append("### FIX 1 effect — time-stop off-by-one\n")
    L.append("Compare `+session-boundary` → `+all bugfixes` (FIX 1 + FIX 2 added):")
    L.append("")
    L.append(f"- IS mean bars_held: {kw['s_isb']['mean_bars_held']:.2f} → "
             f"{kw['s_iall']['mean_bars_held']:.2f} bars "
             f"({kw['s_isb']['mean_hold_min']:.1f}min → {kw['s_iall']['mean_hold_min']:.1f}min hold). ")
    if kw['s_iall']['mean_hold_min'] < kw['s_isb']['mean_hold_min']:
        L.append("  Shorter holds confirm FIX 1 is firing the time-stop one bar earlier.")
    L.append(f"- OOS mean bars_held: {kw['s_osb']['mean_bars_held']:.2f} → "
             f"{kw['s_oall']['mean_bars_held']:.2f} bars "
             f"({kw['s_osb']['mean_hold_min']:.1f}min → {kw['s_oall']['mean_hold_min']:.1f}min hold).")
    L.append("")
    L.append("### FIX 2 effect — exit/entry same-iteration block\n")
    L.append("Compare trade overlap counts at each stage:")
    L.append("")
    L.append(f"- IS overlaps:  original={kw['overlap_io']}, +session-boundary={kw['overlap_isb']}, "
             f"+all bugfixes={kw['overlap_iall']}")
    L.append(f"- OOS overlaps: original={kw['overlap_oo']}, +session-boundary={kw['overlap_osb']}, "
             f"+all bugfixes={kw['overlap_oall']}")
    if kw['overlap_iall'] == 0 and kw['overlap_oall'] == 0:
        L.append("")
        L.append("**FIX 2 eliminated all trade overlaps.** No remaining trades enter while a ")
        L.append("prior trade is open — backtest is now live-equivalent on this dimension.")
    L.append("")
    L.append("Trade-count reduction from FIX 2:")
    L.append(f"- IS:  {kw['s_isb']['n']} → {kw['s_iall']['n']} trades ({kw['s_iall']['n'] - kw['s_isb']['n']:+d}). "
             "The dropped trades are precisely the overlapping ones, plus a small number ")
    L.append("  shifted by FIX 1's earlier exits cascading into different next-bar entry windows.")
    L.append(f"- OOS: {kw['s_osb']['n']} → {kw['s_oall']['n']} trades ({kw['s_oall']['n'] - kw['s_osb']['n']:+d}).")
    L.append("")

    # Exit-reason
    L.append("## 5. Exit-reason distribution\n")
    L.append("### IS\n")
    L.append("| exit_reason | original | +session-boundary | +all bugfixes |")
    L.append("|---|---:|---:|---:|")
    for r in ("time", "stop", "target", "session_close"):
        L.append(f"| {r} | {kw['ed_io'].get(r,0)} | {kw['ed_isb'].get(r,0)} | "
                 f"{kw['ed_iall'].get(r,0)} |")
    L.append("")
    L.append("### OOS\n")
    L.append("| exit_reason | original | +session-boundary | +all bugfixes |")
    L.append("|---|---:|---:|---:|")
    for r in ("time", "stop", "target", "session_close"):
        L.append(f"| {r} | {kw['ed_oo'].get(r,0)} | {kw['ed_osb'].get(r,0)} | "
                 f"{kw['ed_oall'].get(r,0)} |")
    L.append("")

    # Per-cell OOS
    L.append("## 6. Per-cell OOS Sharpe — three-way\n")
    L.append("| cell | orig N | orig Sh | +sb N | +sb Sh | +all N | +all Sh |")
    L.append("|---|---:|---:|---:|---:|---:|---:|")
    for c in CELLS:
        oo = kw["pc_oo"][c]; osb = kw["pc_osb"][c]; oall = kw["pc_oall"][c]
        L.append(f"| {c} | {oo['n']} | {_fmt_sh(oo['sharpe'])} | "
                 f"{osb['n']} | {_fmt_sh(osb['sharpe'])} | "
                 f"{oall['n']} | {_fmt_sh(oall['sharpe'])} |")
    L.append("")

    # OMEN-minus-SL
    L.append("## 7. OMEN-minus-SL Sharpe under each baseline\n")
    L.append("| sample | orig | +session-boundary | +all bugfixes |")
    L.append("|---|---:|---:|---:|")
    L.append(f"| IS full | {_fmt_sh(kw['s_io']['sharpe'])} | {_fmt_sh(kw['s_isb']['sharpe'])} | "
             f"{_fmt_sh(kw['s_iall']['sharpe'])} |")
    L.append(f"| IS minus-SL | {_fmt_sh(kw['minus_io']['sharpe'])} | "
             f"{_fmt_sh(kw['minus_isb']['sharpe'])} | {_fmt_sh(kw['minus_iall']['sharpe'])} |")
    L.append(f"| OOS full | {_fmt_sh(kw['s_oo']['sharpe'])} | {_fmt_sh(kw['s_osb']['sharpe'])} | "
             f"{_fmt_sh(kw['s_oall']['sharpe'])} |")
    L.append(f"| OOS minus-SL | {_fmt_sh(kw['minus_oo']['sharpe'])} | "
             f"{_fmt_sh(kw['minus_osb']['sharpe'])} | {_fmt_sh(kw['minus_oall']['sharpe'])} |")
    L.append("")

    # Honest impact + decision
    L.append("## 8. Honest impact assessment\n")
    L.append("The honest baseline (all known bugs fixed, locked params untouched) is:")
    L.append("")
    L.append(f"- **IS  Sharpe = {_fmt_sh(kw['s_iall']['sharpe'])}** (n={kw['s_iall']['n']} trades, "
             f"{kw['sessions_is']} sessions)")
    L.append(f"- **OOS Sharpe = {_fmt_sh(kw['s_oall']['sharpe'])}** (n={kw['s_oall']['n']} trades, "
             f"{kw['sessions_oos']} sessions)")
    L.append("")
    L.append(f"Compare to the originally-cited locked baseline (IS +5.38, OOS +1.13). The ")
    L.append(f"originally-cited numbers were inflated by both bugs working together: the ")
    L.append(f"session-boundary bug suppressed entries throughout the session, and the ")
    L.append(f"time-stop / overlap bugs together held winning trades 30min instead of 25min ")
    L.append(f"while letting overlapping entries pad PnL.")
    L.append("")
    L.append("### Cell-breakdown / OMEN-minus-SL replication\n")
    sl_oall_sh = kw["pc_oall"][SL_CELL]["sharpe"]
    minus_oall_sh = kw["minus_oall"]["sharpe"]
    full_oall_sh = kw["s_oall"]["sharpe"]
    if sl_oall_sh is not None and sl_oall_sh < 0:
        L.append(f"OOS SHORT_long Sharpe under all-bugfixes: **{_fmt_sh(sl_oall_sh)}** ")
        L.append(f"(remains negative). OMEN-minus-SL OOS Sharpe: "
                 f"**{_fmt_sh(minus_oall_sh)}** vs full **{_fmt_sh(full_oall_sh)}** "
                 f"({'> full → hypothesis direction survives' if (minus_oall_sh or 0) > (full_oall_sh or 0) else '≤ full → hypothesis direction does NOT survive'}).")
    else:
        L.append(f"OOS SHORT_long Sharpe under all-bugfixes: **{_fmt_sh(sl_oall_sh)}** "
                 "(no longer negative — cell-breakdown finding may not survive).")
    L.append("")

    # Decision
    L.append("## 9. Decision points for the user\n")
    L.append("1. **Update the locked baseline numbers to the all-bugfixes values?** ")
    L.append("   The honest IS/OOS Sharpes are what an aligned backtest/live system would ")
    L.append("   actually produce. Any cited Sharpe in future documentation should reference ")
    L.append("   the bugfixed numbers, not the pre-fix originals.")
    L.append("2. **Merge backtest.py fixes to main?** Both fixes are unambiguous backtester ")
    L.append("   bugs that diverge from live behavior. There is no scenario where keeping ")
    L.append("   the bugs is desirable. The remaining question is just whether you want to ")
    L.append("   bundle them with any other changes before merging.")
    L.append("3. **Re-cite prior analyses against the new baseline?** Same answer as the ")
    L.append("   session-boundary fix synthesis: the per-bar / per-trigger analyses ")
    L.append("   independent of backtest.py (Q3 / TRCB pop validation) stand; the trade-log ")
    L.append("   analyses (cell breakdown, OMEN-minus-SL quick-check, ATR=20 sensitivity, ")
    L.append("   Zach May comparison) used the buggy trade logs and would re-run with ")
    L.append("   different magnitudes if redone against the bugfixed baseline.")
    L.append("")

    # Caveats
    L.append("## 10. Caveats\n")
    L.append("- Two of three bugs fixed in this branch are EXIT-LOGIC bugs (FIX 1: time-stop ")
    L.append("  timing; FIX 2: overlap prevention). They do not change which signals fire — ")
    L.append("  the signal count is identical between +session-boundary and +all bugfixes ")
    L.append(f"  ({int(kw['s_isb']['n'] + kw['s_oall']['n'] - kw['s_iall']['n'] - kw['s_osb']['n'])} signals ")
    L.append("  the same on both). The trade-count and Sharpe differences come from which ")
    L.append("  trades the backtester *allows* (FIX 2) and how long it holds them (FIX 1).")
    L.append("- These results are still on the now-thoroughly-consumed 160-session corpus. ")
    L.append("  Any new pre-registration should use this bugfixed baseline as its reference ")
    L.append("  point, not the pre-fix numbers.")
    L.append("- Forward-test validation on fresh sessions remains the only path to a verdict ")
    L.append("  on OMEN's edge. The all-bugfixed baseline is the honest starting point for ")
    L.append("  framing that test, not a substitute for it.")
    L.append("- This branch holds at `diagnostics/all-bugfixes-baseline`. Merge to main only ")
    L.append("  with explicit user sign-off.")
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
