"""Synthesis for the microprice continuation-confirmation overlay."""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

REPO = Path("/Users/rafanelson/Omen")
ANALYSIS = REPO / "analysis/microprice-continuation"
RESULTS_CSV = ANALYSIS / "microprice_overlay_results.csv"
OUT_MD = ANALYSIS / "SYNTHESIS.md"
ET = ZoneInfo("America/New_York")

SL_CELL = "SHORT_long"
CELLS = ["LONG_long", "LONG_short", "SHORT_long", "SHORT_short"]

DISCLOSURE = """\
## DISCLOSURE — in-sample exploratory, cannot validate

This is exploratory in-sample analysis. The microprice continuation
parameters (Stoikov formula, 2-tick threshold, 60-second persistence)
were chosen from first principles before seeing this data, but the test
runs on the same 160-session corpus used for:
- TRCB-v1 Phase 2 and post-mortem (Q1-Q4)
- TRCB-v2 Phase 2/3 and Q6-Q8
- Cell-breakdown analysis
- Q9 GEX mechanism diagnostic
- GEX permutation re-run
- All-bugfix baseline

The corpus is thoroughly consumed. Even with first-principles parameters,
results here cannot serve as validation. They serve only to filter:
- If microprice adds substantial Sharpe lift (>0.5): worth pre-registering
  for fresh-data forward test
- If microprice adds nothing or hurts: drop the concept
- If marginal: defer decision

No deployment authorization. No strategy modification. No baseline change.
"""


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


def _stats(df, n_sessions, net_col="net_dollars"):
    if len(df) == 0:
        return {"n": 0, "win_rate": None, "mean": 0.0, "sum": 0.0,
                "sharpe": None, "max_dd": 0.0}
    net = df[net_col]
    return {"n": int(len(df)), "win_rate": float((net > 0).mean()),
             "mean": float(net.mean()), "sum": float(net.sum()),
             "sharpe": _sharpe(net, n_sessions),
             "max_dd": _max_dd(net, df["entry_time_utc"])}


def _fmt_sh(sh): return "—" if sh is None else f"{sh:+.2f}"
def _fmt_wr(wr): return "—" if wr is None else f"{wr*100:.1f}%"


def main() -> int:
    df = pd.read_csv(RESULTS_CSV)
    df["entry_time"] = pd.to_datetime(df["entry_time"], utc=True)
    df["entry_time_utc"] = df["entry_time"]
    df["entry_time_et"] = df["entry_time"].dt.tz_convert(ET)
    df["exit_time"] = pd.to_datetime(df["exit_time"], utc=True)
    df["entry_date"] = df["entry_time_et"].dt.date
    df["microprice_exit_time"] = pd.to_datetime(df["microprice_exit_time"],
                                                  utc=True, errors="coerce")
    # session counts
    n_is_sess = df.loc[df["sample"] == "IS", "entry_date"].nunique()
    n_oos_sess = df.loc[df["sample"] == "OOS", "entry_date"].nunique()

    # Arms (per sample):
    # Arm 1 = full OMEN (original net_dollars)
    # Arm 2 = minus-SL (original net_dollars, exclude SHORT_long)
    # Arm 3 = minus-SL + microprice overlay (arm3_net_dollars, exclude SHORT_long)

    def _arm_stats(sample: str):
        sub = df[df["sample"] == sample].copy()
        n_sess = sub["entry_date"].nunique()
        a1 = _stats(sub, n_sess, "net_dollars")
        sub_ms = sub[sub["cell"] != SL_CELL]
        a2 = _stats(sub_ms, n_sess, "net_dollars")
        a3 = _stats(sub_ms, n_sess, "arm3_net_dollars")
        return n_sess, a1, a2, a3

    is_sess, is_a1, is_a2, is_a3 = _arm_stats("IS")
    oos_sess, oos_a1, oos_a2, oos_a3 = _arm_stats("OOS")

    # Fire-rate diagnostics across BOTH samples
    n_total = len(df)
    n_fired = int(df["microprice_fired"].sum())
    n_evaluable = int(df["microprice_evaluable"].sum())
    n_unevaluable = n_total - n_evaluable
    fire_rate_total = n_fired / n_total
    fire_rate_evaluable = n_fired / max(n_evaluable, 1)

    print("=" * 72)
    print("Microprice overlay — diagnostics")
    print("=" * 72)
    print(f"  trades total            : {n_total}")
    print(f"  microprice evaluable    : {n_evaluable} ({n_evaluable/n_total*100:.1f}%)")
    print(f"  microprice unevaluable  : {n_unevaluable} ({n_unevaluable/n_total*100:.1f}%)")
    print(f"  microprice fired        : {n_fired} (of all: {fire_rate_total*100:.1f}%; "
          f"of evaluable: {fire_rate_evaluable*100:.1f}%)")

    if n_fired == 0:
        print("\n  [FATAL] Microprice never fired. Implementation likely malfunctioning.")
        OUT_MD.parent.mkdir(parents=True, exist_ok=True)
        OUT_MD.write_text("# Microprice overlay — IMPLEMENTATION CHECK FAILED\n\n"
                           "Microprice never fired in any of the 504 trades. The implementation "
                           "is likely malfunctioning. No metrics reported.\n\n"
                           "See implementation script for the persistence logic.\n")
        return 1
    if fire_rate_total > 0.99:
        print("\n  [FATAL] Microprice fired >99% of the time. Implementation likely malfunctioning.")
        OUT_MD.parent.mkdir(parents=True, exist_ok=True)
        OUT_MD.write_text("# Microprice overlay — IMPLEMENTATION CHECK FAILED\n\n"
                           "Microprice fired >99% of trades — way above the 'continuation "
                           "confirmation' interpretation. Implementation likely too sensitive. "
                           "No metrics reported.\n")
        return 1

    # Microprice-fired diagnostics: would-have-been winner vs loser, $ saved/lost
    fired = df[df["microprice_fired"] == True].copy()
    fired["was_winner"] = fired["net_dollars"] > 0
    fired["delta"] = fired["arm3_net_dollars"] - fired["net_dollars"]
    n_was_winner = int(fired["was_winner"].sum())
    n_was_loser = int((~fired["was_winner"]).sum())
    mean_delta = float(fired["delta"].mean()) if len(fired) else 0.0
    sum_delta = float(fired["delta"].sum()) if len(fired) else 0.0
    mean_delta_winners = (float(fired.loc[fired["was_winner"], "delta"].mean())
                          if n_was_winner else 0.0)
    mean_delta_losers = (float(fired.loc[~fired["was_winner"], "delta"].mean())
                         if n_was_loser else 0.0)

    # Time within window when microprice fires
    fired["minutes_in_trade"] = ((fired["microprice_exit_time"]
                                   - fired["entry_time"]).dt.total_seconds() / 60)
    mins_q = fired["minutes_in_trade"].quantile([0.1, 0.25, 0.5, 0.75, 0.9])

    print(f"\n  Fired trades ({n_fired}):")
    print(f"    were going to be WINNERS  : {n_was_winner} ({n_was_winner/n_fired*100:.1f}%)")
    print(f"    were going to be LOSERS   : {n_was_loser} ({n_was_loser/n_fired*100:.1f}%)")
    print(f"    mean Δ (microprice - orig): ${mean_delta:+.2f}/trade  "
          f"sum: ${sum_delta:+.0f}")
    print(f"    Δ on would-have-winners   : ${mean_delta_winners:+.2f}/trade "
          f"({n_was_winner} trades)")
    print(f"    Δ on would-have-losers    : ${mean_delta_losers:+.2f}/trade "
          f"({n_was_loser} trades)")
    print(f"    fire-time min within trade: q10={mins_q[0.10]:.1f}, "
          f"q25={mins_q[0.25]:.1f}, q50={mins_q[0.50]:.1f}, "
          f"q75={mins_q[0.75]:.1f}, q90={mins_q[0.90]:.1f}")

    print("\n  Arms:")
    print(f"  IS  ({is_sess} sessions)")
    for n, a in (("A1 full",   is_a1), ("A2 minus-SL", is_a2),
                  ("A3 minus-SL + microprice", is_a3)):
        print(f"    {n:<28s}  n={a['n']:>3d}  win={_fmt_wr(a['win_rate']):>7s}  "
              f"mean=${a['mean']:>+8.2f}  sum=${a['sum']:>+8.0f}  "
              f"Sharpe={_fmt_sh(a['sharpe']):>7s}  DD=${a['max_dd']:>+8.0f}")
    print(f"  OOS ({oos_sess} sessions)")
    for n, a in (("A1 full",   oos_a1), ("A2 minus-SL", oos_a2),
                  ("A3 minus-SL + microprice", oos_a3)):
        print(f"    {n:<28s}  n={a['n']:>3d}  win={_fmt_wr(a['win_rate']):>7s}  "
              f"mean=${a['mean']:>+8.2f}  sum=${a['sum']:>+8.0f}  "
              f"Sharpe={_fmt_sh(a['sharpe']):>7s}  DD=${a['max_dd']:>+8.0f}")

    # Exit-reason distribution on arm 3 (minus-SL)
    sub_ms_all = df[df["cell"] != SL_CELL]
    arm3_exits = sub_ms_all["arm3_exit_reason"].value_counts().to_dict()
    orig_exits = sub_ms_all["exit_reason"].value_counts().to_dict()
    print("\n  Exit reasons (minus-SL subset, n={}):".format(len(sub_ms_all)))
    for r in ("time", "stop", "target", "microprice", "session_close"):
        print(f"    {r:<14s}  original={orig_exits.get(r,0):>3d}  "
              f"arm3={arm3_exits.get(r,0):>3d}")

    # ---- Markdown synthesis ----
    L: list[str] = []
    L.append("# Microprice continuation overlay — exploratory (THROWAWAY)\n")
    L.append("Branch: `analysis/microprice-continuation-exploratory-throwaway` "
             "(throwaway / archive only; never merges to main).")
    L.append(f"Generated: {datetime.now().isoformat(timespec='seconds')}\n")
    L.append("## 1. Disclosure\n")
    L.append(DISCLOSURE)
    L.append("")
    L.append("## 2. Locked methodology (no tuning)\n")
    L.append("- **Microprice (Stoikov)**: "
             "`(bid_sz·ask_px + ask_sz·bid_px) / (bid_sz + ask_sz)`")
    L.append("- **Adverse threshold**: 2 ticks (0.50 ES points) against the trade direction")
    L.append("- **Persistence**: 60 consecutive seconds of adverse condition required")
    L.append("- **Exit fill**: best bid − 0.5 tick (long) / best ask + 0.5 tick (short) at "
             "the firing second; same per-side slippage as existing time-stop exits")
    L.append("- **Trade pool**: bugfixed IS (257) + bugfixed OOS (247) = 504 trades")
    L.append("- All other OMEN exits unchanged. Microprice fires only if no other exit hit first.")
    L.append("")
    L.append("## 3. Implementation diagnostics\n")
    L.append(f"- Trades total: **{n_total}**")
    L.append(f"- Microprice-evaluable: **{n_evaluable}** "
             f"({n_evaluable/n_total*100:.1f}%) — has book ticks and window ≥ 60s")
    L.append(f"- Microprice fired: **{n_fired}** "
             f"({fire_rate_total*100:.1f}% of all trades; "
             f"{fire_rate_evaluable*100:.1f}% of evaluable trades)")
    L.append("")
    if fire_rate_evaluable < 0.10:
        L.append("⚠ **Fire rate < 10%** on evaluable trades. Microprice contributes too rarely "
                 "to be a meaningful component on this corpus.")
    elif fire_rate_evaluable > 0.50:
        L.append("⚠ **Fire rate > 50%** on evaluable trades. Microprice is acting as a generic "
                 "exit trigger, not a continuation-confirmation. Likely fitting to noise.")
    else:
        L.append(f"Fire rate is in the 10-50% range — within the spec's 'reasonable' window "
                 "(not too rare to matter, not so common it's a generic exit).")
    L.append("")

    # Per-arm tables
    L.append("## 4. Three-arm comparison (per sample)\n")
    L.append("### IS (74 sessions, 257 trades)\n")
    L.append("| arm | N | win | mean $ | sum $ | Sharpe | max DD |")
    L.append("|---|---:|---:|---:|---:|---:|---:|")
    for label, a in (("A1 — full OMEN", is_a1),
                       ("A2 — OMEN-minus-SL", is_a2),
                       ("A3 — OMEN-minus-SL + microprice", is_a3)):
        L.append(f"| {label} | {a['n']} | {_fmt_wr(a['win_rate'])} | "
                 f"${a['mean']:+.2f} | ${a['sum']:+.0f} | "
                 f"{_fmt_sh(a['sharpe'])} | ${a['max_dd']:+.0f} |")
    L.append("")
    L.append("### OOS (72 sessions, 247 trades)\n")
    L.append("| arm | N | win | mean $ | sum $ | Sharpe | max DD |")
    L.append("|---|---:|---:|---:|---:|---:|---:|")
    for label, a in (("A1 — full OMEN", oos_a1),
                       ("A2 — OMEN-minus-SL", oos_a2),
                       ("A3 — OMEN-minus-SL + microprice", oos_a3)):
        L.append(f"| {label} | {a['n']} | {_fmt_wr(a['win_rate'])} | "
                 f"${a['mean']:+.2f} | ${a['sum']:+.0f} | "
                 f"{_fmt_sh(a['sharpe'])} | ${a['max_dd']:+.0f} |")
    L.append("")

    # Sharpe deltas (the headline number)
    is_lift = (is_a3['sharpe'] or 0) - (is_a2['sharpe'] or 0)
    oos_lift = (oos_a3['sharpe'] or 0) - (oos_a2['sharpe'] or 0)
    L.append("### Sharpe lift from microprice overlay (A3 − A2)\n")
    L.append(f"- IS Sharpe lift: **{is_lift:+.2f}** ({_fmt_sh(is_a2['sharpe'])} → "
             f"{_fmt_sh(is_a3['sharpe'])})")
    L.append(f"- OOS Sharpe lift: **{oos_lift:+.2f}** ({_fmt_sh(oos_a2['sharpe'])} → "
             f"{_fmt_sh(oos_a3['sharpe'])})")
    L.append("")

    # Microprice-fired diagnostics
    L.append("## 5. Microprice-fire diagnostics\n")
    L.append(f"Of the {n_fired} trades where microprice fired:")
    L.append(f"- Would have been **winners** under original exit: "
             f"**{n_was_winner}** ({n_was_winner/n_fired*100:.1f}%)")
    L.append(f"- Would have been **losers**: **{n_was_loser}** "
             f"({n_was_loser/n_fired*100:.1f}%)")
    L.append(f"- Mean Δ vs original (microprice − orig): **${mean_delta:+.2f}/trade**")
    L.append(f"- Sum Δ across fired trades: **${sum_delta:+.0f}**")
    L.append(f"  - On would-have-been-winners: ${mean_delta_winners:+.2f}/trade × "
             f"{n_was_winner} trades")
    L.append(f"  - On would-have-been-losers : ${mean_delta_losers:+.2f}/trade × "
             f"{n_was_loser} trades")
    L.append("")
    L.append("### When does microprice fire within the trade?\n")
    L.append("| quantile | minutes into trade |")
    L.append("|---:|---:|")
    for q in (0.10, 0.25, 0.50, 0.75, 0.90):
        L.append(f"| q{int(q*100)} | {mins_q[q]:.1f} |")
    L.append("")

    L.append("## 6. Exit-reason distribution (minus-SL subset)\n")
    L.append("| exit_reason | A2 original | A3 with microprice |")
    L.append("|---|---:|---:|")
    for r in ("time", "stop", "target", "microprice", "session_close"):
        L.append(f"| {r} | {orig_exits.get(r,0)} | {arm3_exits.get(r,0)} |")
    L.append("")

    # ---- Honest verdict ----
    L.append("## 7. Honest verdict\n")

    # Decision criteria from the spec
    oos_qualifies = oos_lift > 0.5
    too_often = fire_rate_evaluable > 0.50
    too_rare = fire_rate_evaluable < 0.10
    cuts_winners = n_was_winner > n_was_loser

    if too_rare:
        verdict = "DROP CONCEPT (too rare)"
        rationale = (f"Microprice fires on only {fire_rate_evaluable*100:.1f}% of evaluable "
                     "trades. The contribution to overall strategy P&L is statistically too "
                     "small to matter, even if directionally correct.")
    elif too_often:
        verdict = "DROP CONCEPT (too generic)"
        rationale = (f"Microprice fires on {fire_rate_evaluable*100:.1f}% of evaluable trades. "
                     "That's not 'continuation confirmation' — it's a generic exit trigger. "
                     "The 2-tick / 60-sec spec is too sensitive for this corpus.")
    elif oos_lift > 0.5 and not cuts_winners:
        verdict = "WORTH PRE-REGISTERING FOR FRESH DATA"
        rationale = (f"OOS Sharpe lift of {oos_lift:+.2f} clears the 0.5-point bar, AND "
                     f"microprice cuts more losers ({n_was_loser}) than winners "
                     f"({n_was_winner}). Concept is directionally sound and meaningful on "
                     "consumed data. Forward-test pre-registration would be the legitimate "
                     "next step.")
    elif oos_lift > 0.5 and cuts_winners:
        verdict = "AMBIGUOUS (defer)"
        rationale = (f"OOS Sharpe lift of {oos_lift:+.2f} is meaningful, BUT microprice cuts "
                     f"more winners ({n_was_winner}) than losers ({n_was_loser}). The Sharpe "
                     "improvement may be coming from variance reduction on losers being "
                     "smaller in magnitude than the cap on winners — fragile and "
                     "sensitive to corpus regime.")
    elif abs(oos_lift) < 0.3:
        verdict = "AMBIGUOUS (defer)"
        rationale = (f"OOS Sharpe lift of {oos_lift:+.2f} is below the 0.5-point bar and "
                     "within the noise floor of small samples. Cannot distinguish "
                     "from chance.")
    else:
        verdict = "DROP CONCEPT"
        rationale = (f"OOS Sharpe lift of {oos_lift:+.2f} is negative or near zero. "
                     "Microprice is not adding value on this corpus.")
    L.append(f"**Verdict: {verdict}**")
    L.append("")
    L.append(rationale)
    L.append("")
    L.append("### Reading the criteria explicitly\n")
    L.append(f"- OOS Sharpe lift > 0.5: **{'YES' if oos_qualifies else 'NO'}** "
             f"(actual {oos_lift:+.2f})")
    L.append(f"- Fire rate in 10-50% window: **"
             f"{'YES' if not (too_rare or too_often) else 'NO'}** "
             f"(actual {fire_rate_evaluable*100:.1f}%)")
    L.append(f"- Cuts losers > winners: **{'YES' if not cuts_winners else 'NO'}** "
             f"({n_was_loser} losers, {n_was_winner} winners)")
    L.append("")

    # Caveats
    L.append("## 8. Caveats\n")
    L.append("- **In-sample on consumed corpus.** Cannot validate the concept regardless of "
             "result. The 'first-principles parameters' framing is good methodology but does ")
    L.append("  not undo data contamination from the 9 prior analyses on this corpus.")
    L.append("- **The minus-SL framing** (excluding SHORT_long) is itself a consumed-data ")
    L.append("  hypothesis. Adding microprice on top conjures a two-step strategy where both ")
    L.append("  steps were chosen with knowledge of this data.")
    L.append("- **Slippage model**: 0.5 tick adverse on the microprice exit matches the locked ")
    L.append("  CostModel for time-stop exits. Real intra-bar fills may behave differently.")
    L.append("- **Result is brittle to parameter choice**. The 2-tick / 60-sec spec was ")
    L.append("  pre-stated; running the same overlay with 3-tick / 90-sec would give different ")
    L.append("  numbers. The spec parameters are not a knob to tune — but they are also not a ")
    L.append("  guarantee that the chosen values are the right ones for fresh data.")
    L.append("- **The pre-registered OMEN-minus-SL forward test (commit `9c1c22f`) does NOT ")
    L.append("  include microprice.** Any forward-test pre-reg involving microprice would need ")
    L.append("  to be written separately and run on data not yet consumed.")
    L.append("")
    OUT_MD.write_text("\n".join(L) + "\n")
    print(f"\nSaved synthesis: {OUT_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
