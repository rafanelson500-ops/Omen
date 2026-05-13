"""Step 2 — metrics + SYNTHESIS for OMEN-minus-SL bugfixed fresh-session re-run.

Compares:
  * buggy historical IS         (174 trades, Sharpe +5.38, locked baseline pre-fix)
  * buggy historical OOS        (158 trades, Sharpe +1.13, locked baseline pre-fix)
  * bugfixed historical IS      (257 trades, Sharpe +2.57, all-bugfixes branch)
  * bugfixed historical OOS     (247 trades, Sharpe +0.51, all-bugfixes branch)
  * buggy fresh                 (18 trades,  Sharpe +0.30, original quick-check)
  * bugfixed fresh              (this run)
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

REPO = Path("/Users/rafanelson/Omen")
ANALYSIS = REPO / "analysis/omen-minus-sl-bugfixed"
ET = ZoneInfo("America/New_York")

FRESH_CSV = ANALYSIS / "fresh_trades_raw_bugfixed.csv"
FULL_CSV  = ANALYSIS / "fresh_trades_full_omen_bugfixed.csv"
SL_CSV    = ANALYSIS / "fresh_trades_omen_minus_sl_bugfixed.csv"
OUT_MD    = ANALYSIS / "SYNTHESIS.md"

SL_CELL = "SHORT_long"
CELLS = ["LONG_long", "LONG_short", "SHORT_long", "SHORT_short"]

# Prior reference numbers (from already-committed analyses)
PRIORS = {
    "buggy_IS": {"n": 174, "full_sh": +5.38, "minus_sh": +4.36,
                  "sl_n": 32, "sl_sh": +3.23, "sessions": 80},
    "buggy_OOS": {"n": 158, "full_sh": +1.13, "minus_sh": +2.79,
                   "sl_n": 48, "sl_sh": -1.95, "sessions": 76},
    "bugfixed_IS": {"n": 257, "full_sh": +2.57, "minus_sh": +1.23,
                     "sl_n": 65, "sl_sh": +3.30, "sessions": 74},
    "bugfixed_OOS": {"n": 247, "full_sh": +0.51, "minus_sh": +1.88,
                      "sl_n": 68, "sl_sh": -1.70, "sessions": 72},
    "buggy_fresh": {"n": 18, "full_sh": +0.30, "minus_sh": +1.84,
                     "sl_n": 1, "sl_sh": None, "sessions": 8},
}


def _load(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["entry_time"] = pd.to_datetime(df["entry_time"], utc=True)
    df["entry_time_utc"] = df["entry_time"]
    df["entry_time_et"] = df["entry_time"].dt.tz_convert(ET)
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


def _stats(df, n_sessions, min_n=10):
    if len(df) == 0:
        return {"n": 0, "win_rate": None, "mean": 0.0, "sum": 0.0,
                "sharpe": None, "max_dd": 0.0}
    net = df["net_dollars"]
    return {"n": int(len(df)), "win_rate": float((net > 0).mean()),
             "mean": float(net.mean()), "sum": float(net.sum()),
             "sharpe": _sharpe(net, n_sessions, min_n=min_n),
             "max_dd": _max_dd(net, df["entry_time_utc"])}


def _fmt_sh(sh): return "—" if sh is None else f"{sh:+.2f}"
def _fmt_wr(wr): return "—" if wr is None else f"{wr*100:.1f}%"


DISCLOSURE = """\
## DISCLOSURE — fourth analysis on the same fresh sessions

This is a re-run of the OMEN-minus-SHORT_long quick-check on fresh
sessions, now using the bugfixed infrastructure (features.py
session-boundary fix + backtest.py time-stop and overlap fixes, all
merged to main).

These same fresh sessions have been used for:
1. Original quick-check (buggy code)
2. ATR=20 sensitivity variant
3. Zach's May params comparison
4. Now this bugfixed re-run

Cumulative consumption: 4 analyses on the same 8-9 sessions. The data
is no longer clean for forward-test purposes.

Sample size remains too small for any verdict (~16-20 trades expected).
Results inform planning only. Proper forward-test pre-registration on
30+ accumulated fresh sessions remains the required validation path.
"""


def main() -> int:
    trades = _load(FRESH_CSV)
    n_sessions = trades["entry_date"].nunique()
    dates = sorted(trades["entry_date"].unique())

    full = trades.copy()
    minus = trades[trades["cell"] != SL_CELL].copy()
    full.to_csv(FULL_CSV, index=False)
    minus.to_csv(SL_CSV, index=False)
    print(f"Full saved : {FULL_CSV} ({len(full)} trades)")
    print(f"Minus-SL  : {SL_CSV} ({len(minus)} trades)")

    full_st = _stats(full, n_sessions)
    minus_st = _stats(minus, n_sessions)
    per_cell = {c: _stats(trades[trades["cell"] == c], n_sessions, min_n=10)
                for c in CELLS}
    exits = trades["exit_reason"].value_counts().to_dict()

    print("\n=== Bugfixed fresh-session aggregate ===")
    print(f"  full_omen      n={full_st['n']:>3d}  win={_fmt_wr(full_st['win_rate']):>7s}  "
          f"mean=${full_st['mean']:>+7.2f}  sum=${full_st['sum']:>+8.0f}  "
          f"Sharpe={_fmt_sh(full_st['sharpe']):>7s}  DD=${full_st['max_dd']:>+8.0f}")
    print(f"  omen_minus_sl  n={minus_st['n']:>3d}  win={_fmt_wr(minus_st['win_rate']):>7s}  "
          f"mean=${minus_st['mean']:>+7.2f}  sum=${minus_st['sum']:>+8.0f}  "
          f"Sharpe={_fmt_sh(minus_st['sharpe']):>7s}  DD=${minus_st['max_dd']:>+8.0f}")
    print("\nPer-cell:")
    for c in CELLS:
        s = per_cell[c]
        print(f"  {c:<12s}  n={s['n']:>3d}  mean=${s['mean']:>+8.2f}  "
              f"sum=${s['sum']:>+7.0f}  Sharpe={_fmt_sh(s['sharpe']):>7s}")
    print("\nExit reasons:", exits)

    # Per-session detail
    print("\nPer-session count + net $:")
    for d in dates:
        sub = trades[trades["entry_date"] == d]
        print(f"  {d.isoformat()}  n={len(sub):>2d}  net=${sub['net_dollars'].sum():>+8.2f}")

    # Six-way comparison
    print("\n=== Six-way comparison ===")
    print(f"  {'sample':<18s}  {'N':>4s}  {'sess':>4s}  "
          f"{'full Sh':>8s}  {'minus-SL Sh':>11s}  {'SL n':>5s}  {'SL Sh':>7s}")
    for label, p in (("buggy IS",        PRIORS["buggy_IS"]),
                      ("buggy OOS",       PRIORS["buggy_OOS"]),
                      ("bugfixed IS",     PRIORS["bugfixed_IS"]),
                      ("bugfixed OOS",    PRIORS["bugfixed_OOS"]),
                      ("buggy fresh",     PRIORS["buggy_fresh"])):
        sl_sh = _fmt_sh(p['sl_sh'])
        print(f"  {label:<18s}  {p['n']:>4d}  {p['sessions']:>4d}  "
              f"{_fmt_sh(p['full_sh']):>8s}  {_fmt_sh(p['minus_sh']):>11s}  "
              f"{p['sl_n']:>5d}  {sl_sh:>7s}")
    sl_st = per_cell[SL_CELL]
    print(f"  {'bugfixed fresh':<18s}  {full_st['n']:>4d}  {n_sessions:>4d}  "
          f"{_fmt_sh(full_st['sharpe']):>8s}  {_fmt_sh(minus_st['sharpe']):>11s}  "
          f"{sl_st['n']:>5d}  {_fmt_sh(sl_st['sharpe']):>7s}")

    md = _synthesize(trades=trades, dates=dates, n_sessions=n_sessions,
                      full=full_st, minus=minus_st, per_cell=per_cell,
                      exits=exits, sl_trades=trades[trades["cell"] == SL_CELL])
    OUT_MD.write_text(md)
    print(f"\nSaved synthesis: {OUT_MD}")
    return 0


def _synthesize(**kw) -> str:
    L: list[str] = []
    L.append("# OMEN-minus-SL bugfixed fresh-session quick-check (THROWAWAY)\n")
    L.append("Branch: `analysis/omen-minus-sl-bugfixed-quickcheck-throwaway` "
             "(throwaway / archive only; never merges to main).")
    L.append(f"Generated: {datetime.now().isoformat(timespec='seconds')}\n")
    L.append("## 1. Disclosure\n")
    L.append(DISCLOSURE)
    L.append("")

    full = kw["full"]; minus = kw["minus"]; pc = kw["per_cell"]
    n_sessions = kw["n_sessions"]; dates = kw["dates"]

    # Setup
    L.append("## 2. Setup\n")
    L.append(f"- Fresh sessions analyzed: **{n_sessions}** "
             f"({dates[0].isoformat()} → {dates[-1].isoformat()})")
    L.append("  - Excluded: 2026-04-29 (GexBot `.missing` sentinel) and 2026-05-12 "
             "(ES 1s bars not yet pulled).")
    L.append("- Locked baseline params: z=1.8, blackout_lunch=True, stop=2.0×ATR, "
             "target=4.5×ATR, time_stop=25min, ATR=14, bar_freq=5min.")
    L.append("- Infrastructure: main with all three bug fixes (commits c333405 + c52a9ab).")
    L.append("")

    # Aggregate
    L.append("## 3. Aggregate metrics on bugfixed fresh-session run\n")
    L.append("| arm | N | win | mean $ | sum $ | Sharpe | max DD |")
    L.append("|---|---:|---:|---:|---:|---:|---:|")
    for label, st in (("full_omen_bugfixed", full),
                       ("omen_minus_sl_bugfixed", minus)):
        L.append(f"| {label} | {st['n']} | {_fmt_wr(st['win_rate'])} | "
                 f"${st['mean']:+.2f} | ${st['sum']:+.0f} | "
                 f"{_fmt_sh(st['sharpe'])} | ${st['max_dd']:+.0f} |")
    L.append("")

    # Per-cell
    L.append("## 4. Per-cell breakdown\n")
    L.append("| cell | N | mean $ | sum $ | Sharpe (if N≥10) |")
    L.append("|---|---:|---:|---:|---:|")
    for c in CELLS:
        s = pc[c]
        sh_str = _fmt_sh(s["sharpe"]) if s["n"] >= 10 else f"(n<10: n={s['n']})"
        L.append(f"| {c} | {s['n']} | ${s['mean']:+.2f} | ${s['sum']:+.0f} | {sh_str} |")
    L.append("")

    # Exit reasons
    L.append("### Exit-reason distribution (fresh, bugfixed)\n")
    L.append("| exit_reason | count |")
    L.append("|---|---:|")
    for r in ("time", "stop", "target", "trail", "session_close"):
        L.append(f"| {r} | {kw['exits'].get(r, 0)} |")
    L.append("")

    # Six-way comparison
    L.append("## 5. Six-way comparison\n")
    L.append("| sample | N | sessions | full Sharpe | minus-SL Sharpe | SHORT_long N | SHORT_long Sharpe |")
    L.append("|---|---:|---:|---:|---:|---:|---:|")
    for label, p in (("buggy IS",        PRIORS["buggy_IS"]),
                      ("buggy OOS",       PRIORS["buggy_OOS"]),
                      ("bugfixed IS",     PRIORS["bugfixed_IS"]),
                      ("bugfixed OOS",    PRIORS["bugfixed_OOS"]),
                      ("buggy fresh",     PRIORS["buggy_fresh"])):
        sl_sh = _fmt_sh(p["sl_sh"]) if p["sl_sh"] is not None else "(n=1)"
        L.append(f"| {label} | {p['n']} | {p['sessions']} | "
                 f"{_fmt_sh(p['full_sh'])} | {_fmt_sh(p['minus_sh'])} | "
                 f"{p['sl_n']} | {sl_sh} |")
    sl_st = pc[SL_CELL]
    sl_sh_str = _fmt_sh(sl_st["sharpe"]) if sl_st["n"] >= 10 else f"(n={sl_st['n']})"
    L.append(f"| **bugfixed fresh (this)** | **{full['n']}** | **{n_sessions}** | "
             f"**{_fmt_sh(full['sharpe'])}** | **{_fmt_sh(minus['sharpe'])}** | "
             f"**{sl_st['n']}** | **{sl_sh_str}** |")
    L.append("")

    # Honest interpretation
    L.append("## 6. Honest interpretation\n")

    # Compare bugfixed fresh full vs buggy fresh full
    L.append("### Bugfixed code vs buggy code on the same fresh sessions\n")
    bf_full = full["sharpe"]; bg_full = PRIORS["buggy_fresh"]["full_sh"]
    bf_minus = minus["sharpe"]; bg_minus = PRIORS["buggy_fresh"]["minus_sh"]
    L.append(f"- Buggy fresh full Sharpe = {_fmt_sh(bg_full)} (n=18). ")
    L.append(f"  Bugfixed fresh full Sharpe = {_fmt_sh(bf_full)} (n={full['n']}). ")
    if bf_full is not None and bf_full > bg_full + 0.5:
        L.append("  Bugfixed code raises the fresh full Sharpe notably.")
    elif bf_full is not None and bf_full < bg_full - 0.5:
        L.append("  Bugfixed code lowers the fresh full Sharpe notably.")
    else:
        L.append("  Bugfixed and buggy fresh full Sharpes are roughly comparable.")
    L.append("")
    L.append(f"- Buggy fresh minus-SL Sharpe = {_fmt_sh(bg_minus)} (n=17). ")
    L.append(f"  Bugfixed fresh minus-SL Sharpe = {_fmt_sh(bf_minus)} (n={minus['n']}). ")
    if bf_minus is not None and bf_minus > bg_minus + 0.5:
        L.append("  Bugfixed code raises the fresh minus-SL Sharpe notably.")
    elif bf_minus is not None and bf_minus < bg_minus - 0.5:
        L.append("  Bugfixed code lowers the fresh minus-SL Sharpe notably.")
    else:
        L.append("  Bugfixed and buggy fresh minus-SL Sharpes are roughly comparable.")
    L.append("")

    # Compare fresh bugfixed vs historical bugfixed OOS
    L.append("### Bugfixed fresh vs bugfixed historical OOS\n")
    L.append(f"- Bugfixed historical OOS (n=247, 72 sessions): full +0.51, minus-SL +1.88.")
    L.append(f"- Bugfixed fresh (n={full['n']}, {n_sessions} sessions): "
             f"full {_fmt_sh(full['sharpe'])}, minus-SL {_fmt_sh(minus['sharpe'])}.")
    if full["sharpe"] is not None:
        if full["sharpe"] > 1.0 and full["sharpe"] > 0.51 + 1.0:
            L.append("  Fresh full Sharpe is materially higher than historical OOS — could be ")
            L.append("  regime tailwind, could be small-sample noise. Cannot distinguish at n≈24.")
        elif full["sharpe"] < -0.5:
            L.append("  Fresh full Sharpe is materially lower than historical OOS — could be ")
            L.append("  regime headwind, could be small-sample noise.")
        else:
            L.append("  Fresh full Sharpe is in the same neighborhood as historical OOS.")
    L.append("")

    # SHORT_long fragility check
    sl_st_local = pc[SL_CELL]
    L.append("### Cell-exclusion hypothesis on bugfixed fresh\n")
    L.append(f"- SHORT_long count on bugfixed fresh: **n={sl_st_local['n']}**, "
             f"sum=${sl_st_local['sum']:+.0f}, mean=${sl_st_local['mean']:+.2f}.")
    if sl_st_local["n"] <= 3:
        L.append(f"")
        L.append(f"**The cell-exclusion result still rests on a tiny SHORT_long sample "
                 f"(n={sl_st_local['n']}).** The minus-SL Sharpe lift "
                 f"({_fmt_sh(full['sharpe'])} → {_fmt_sh(minus['sharpe'])}) is driven by ")
        L.append(f"removing {sl_st_local['n']} trade(s). On any specific tiny sample like this, ")
        L.append("this lift can move dramatically with a single different SHORT_long outcome — ")
        L.append("the hypothesis cannot be evaluated rigorously here.")
        ss = pc["SHORT_short"]
        if ss["sum"] < sl_st_local["sum"] and ss["sum"] < 0:
            L.append("")
            L.append(f"By total $ damage, SHORT_short (n={ss['n']}, sum=${ss['sum']:+.0f}) is "
                     f"contributing more drag than SHORT_long (n={sl_st_local['n']}, "
                     f"sum=${sl_st_local['sum']:+.0f}) on this window. If the cell-exclusion ")
            L.append("hypothesis is right *in general*, the fresh sample isn't where to test it.")
    else:
        L.append(f"")
        L.append(f"SHORT_long has n={sl_st_local['n']} on bugfixed fresh. Sharpe is "
                 f"{_fmt_sh(sl_st_local['sharpe'])}.")
    L.append("")

    # Decision-relevant findings
    L.append("## 7. Decision-relevant findings\n")
    L.append(f"1. **Full OMEN bugfixed fresh ({_fmt_sh(full['sharpe'])}) vs bugfixed "
             f"historical OOS (+0.51)**: ")
    if full["sharpe"] is None:
        L.append("   N too small to compute Sharpe.")
    elif abs(full["sharpe"] - 0.51) > 1.5:
        L.append(f"   Material difference (Δ {full['sharpe'] - 0.51:+.2f}). Worth noting but ")
        L.append("   not interpretable at n≈24.")
    else:
        L.append(f"   Differences are within the noise floor of n≈24 trade samples.")
    L.append("")
    L.append(f"2. **SHORT_long count = {sl_st_local['n']} on bugfixed fresh.**")
    if sl_st_local["n"] <= 3:
        L.append("   The cell-exclusion hypothesis (OMEN-minus-SL > OMEN) cannot be rigorously ")
        L.append(f"   evaluated when the excluded cell has only {sl_st_local['n']} trade(s). ")
        L.append("   This holds regardless of which infrastructure produced the trades.")
    L.append("")
    L.append("3. **Direction of cell-exclusion effect**: ")
    if (full["sharpe"] is not None and minus["sharpe"] is not None
        and minus["sharpe"] > full["sharpe"]):
        L.append("   `minus_sl_bugfixed Sharpe > full_omen_bugfixed Sharpe` "
                 "(directionally consistent with the OOS-247 finding +1.88 > +0.51).")
    elif (full["sharpe"] is not None and minus["sharpe"] is not None
          and minus["sharpe"] <= full["sharpe"]):
        L.append("   `minus_sl_bugfixed Sharpe <= full_omen_bugfixed Sharpe` "
                 "(NOT directionally consistent with the OOS-247 finding).")
    else:
        L.append("   N too small to compute one or both Sharpes.")
    L.append("")
    L.append("4. **What this analysis cannot tell us**: whether the cell-exclusion edge is real, ")
    L.append("   whether it generalizes beyond this window, whether the bugfixed infrastructure ")
    L.append("   changes the right cells. Forward-test pre-registration on 30+ accumulated fresh ")
    L.append("   sessions remains the only path to those answers.")
    L.append("")

    # Caveats
    L.append("## 8. Caveats (mandatory)\n")
    L.append(f"- **This is the fourth analysis on the same 8 fresh sessions** ")
    L.append("  (original quick-check, ATR=20 variant, Zach May, this bugfixed re-run). ")
    L.append("  These sessions are cumulatively consumed for the cell-exclusion hypothesis.")
    L.append(f"- **Sample size {full['n']} trades / {n_sessions} sessions is far too small** for ")
    L.append("  any statistical verdict.")
    L.append(f"- **SHORT_long has n={sl_st_local['n']} on this sample**; whether the cell-exclusion ")
    L.append("  pattern survives is essentially undetermined by these trades.")
    L.append("- **No deployment decision is authorized by this analysis** regardless of how the ")
    L.append("  numbers look.")
    L.append("- **Forward-test pre-registration on 30+ accumulated unconsumed sessions** is the ")
    L.append("  only path to validation. That work has not yet begun.")
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
