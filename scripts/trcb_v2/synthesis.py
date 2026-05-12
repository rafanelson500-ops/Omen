"""TRCB-v2 SYNTHESIS — combine Phase 2 + Phase 3 into a single report.

THROWAWAY IN-SAMPLE ANALYSIS. See common.CRITICAL_DISCLOSURE.

This script reads previously-saved outputs:
  - analysis/trcb-v2-consumed/phase2_population_results.csv
  - analysis/trcb-v2-consumed/phase3_summary_table.csv
  - diagnostics/mbp10-trcb-v1/phase2_population_results.csv   (v1 reference)

and emits analysis/trcb-v2-consumed/SYNTHESIS.md.
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (  # noqa: E402
    CRITICAL_DISCLOSURE, DELTA_RATIO, FORWARD_HORIZONS_MIN,
    OUTPUT_ANALYSIS_DIR, PHASE2_RESULTS_CSV, PHASE3_RESULTS_CSV,
    PRICE_ATR_MULT, SYNTHESIS_MD, V1_PHASE2_CSV, VOLUME_MULT, WINDOW_SECONDS,
)

PHASE3_SUMMARY_CSV = OUTPUT_ANALYSIS_DIR / "phase3_summary_table.csv"


def _stat_block(s: pd.Series) -> dict:
    if len(s) == 0:
        return {"n": 0}
    std = float(s.std(ddof=1)) if len(s) > 1 else float("nan")
    t = float(s.mean() / (std / np.sqrt(len(s)))) if len(s) > 1 and std > 0 else float("nan")
    return {"n": len(s), "mean": float(s.mean()), "median": float(s.median()),
            "std": std, "t_vs_zero": t,
            "pct_positive": float((s > 0).mean())}


def main() -> None:
    OUTPUT_ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)
    # v2 Phase 2
    p2 = pd.read_csv(PHASE2_RESULTS_CSV)
    n_long = int(p2["trcb_long"].sum())
    n_short = int(p2["trcb_short"].sum())
    n_trig = n_long + n_short
    trig_mask = p2["trcb_long"] | p2["trcb_short"]
    horizon_stats = {}
    for h in FORWARD_HORIZONS_MIN:
        col = f"fwd_ret_{h}min_signed"
        raw_col = f"fwd_ret_{h}min_raw"
        if col in p2.columns:
            horizon_stats[h] = {
                "trig": _stat_block(p2.loc[trig_mask, col].dropna()),
                "all_raw": _stat_block(p2[raw_col].dropna()),
                "long": _stat_block(p2.loc[p2["trcb_long"], col].dropna()),
                "short": _stat_block(p2.loc[p2["trcb_short"], col].dropna()),
            }

    # v1 Phase 2 (reference)
    v1 = pd.read_csv(V1_PHASE2_CSV)
    v1_long = int(v1["trcb_long"].sum())
    v1_short = int(v1["trcb_short"].sum())
    v1_trig_mask = v1["trcb_long"] | v1["trcb_short"]
    v1_signed = v1.loc[v1_trig_mask, "fwd_ret_25min_signed"].dropna()
    v1_signed_stat = _stat_block(v1_signed)

    # Phase 3
    p3 = pd.read_csv(PHASE3_SUMMARY_CSV)

    # ---- Build markdown ----
    L: list[str] = []
    L.append("# TRCB-v2 SYNTHESIS — Consumed-Data Test (IN-SAMPLE, THROWAWAY)")
    L.append("")
    L.append(f"**Generated:** {datetime.now().isoformat(timespec='seconds')}")
    L.append(f"**Branch:** `analysis/trcb-v2-consumed-data-test-throwaway` ")
    L.append(f"(throwaway / archive only; never merges to main)")
    L.append("")
    L.append("## 1. Critical Disclosure")
    L.append("")
    # Strip the embedded `## CRITICAL...` header line; we have our own H2 above.
    disclosure_body = "\n".join(
        ln for ln in CRITICAL_DISCLOSURE.splitlines()
        if not ln.strip().startswith("## CRITICAL METHODOLOGICAL DISCLOSURE")
    ).strip()
    L.append(disclosure_body)
    L.append("")

    L.append("## 2. Phase 2 — population numbers vs TRCB-v1 reference")
    L.append("")
    L.append("Both v1 and v2 evaluated on the identical 160-session corpus "
             "(2025-09-08 → 2026-04-27).")
    L.append("")
    L.append("### Parameters compared")
    L.append("| param | TRCB-v1 (pre-reg b75e995) | TRCB-v2 (in-sample) |")
    L.append("|---|---|---|")
    L.append(f"| WINDOW_SECONDS | 60 | **{WINDOW_SECONDS}** |")
    L.append(f"| VOLUME_MULT | 1.0 | {VOLUME_MULT} |")
    L.append(f"| DELTA_RATIO  | 2.0 | **{DELTA_RATIO}** |")
    L.append(f"| PRICE_ATR_MULT | 0.25 | {PRICE_ATR_MULT} |")
    L.append("")
    L.append("### Trigger counts")
    L.append("| version | long | short | total | rate of evaluable |")
    L.append("|---|---:|---:|---:|---:|")
    eval_bars = 11989  # from Phase 2 run (constant across v1 and v2 on same corpus)
    L.append(f"| TRCB-v1 | {v1_long:,} | {v1_short:,} | {v1_long+v1_short:,} | "
             f"{(v1_long+v1_short)/eval_bars*100:.4f}% |")
    L.append(f"| TRCB-v2 | {n_long:,} | {n_short:,} | {n_trig:,} | "
             f"{n_trig/eval_bars*100:.4f}% |")
    L.append("")
    L.append("### Forward-return signal — v2 (this analysis)")
    L.append("| horizon | n | mean signed | t vs 0 | %>0 |")
    L.append("|---|---:|---:|---:|---:|")
    for h in FORWARD_HORIZONS_MIN:
        s = horizon_stats[h]["trig"]
        L.append(f"| {h} min | {s.get('n',0):,} | {s.get('mean',0):+.4f} | "
                 f"{s.get('t_vs_zero',0):+.4f} | {s.get('pct_positive',0)*100:.2f}% |")
    L.append("")
    L.append("### Forward-return signal — v1 (reference, 25-min only)")
    L.append(f"- n = {v1_signed_stat.get('n', 0)}  "
             f"mean = **{v1_signed_stat.get('mean', float('nan')):+.4f}** pts  "
             f"t = **{v1_signed_stat.get('t_vs_zero', float('nan')):+.4f}**  "
             f"%>0 = **{v1_signed_stat.get('pct_positive', 0)*100:.2f}%**")
    L.append("")
    L.append("### Per-direction signal at each horizon — v2")
    L.append("| horizon | long n | long mean | long t | short n | short mean | short t |")
    L.append("|---|---:|---:|---:|---:|---:|---:|")
    for h in FORWARD_HORIZONS_MIN:
        sl = horizon_stats[h]["long"]; ss = horizon_stats[h]["short"]
        L.append(f"| {h} min | {sl.get('n',0)} | {sl.get('mean',float('nan')):+.4f} | "
                 f"{sl.get('t_vs_zero',float('nan')):+.4f} | "
                 f"{ss.get('n',0)} | {ss.get('mean',float('nan')):+.4f} | "
                 f"{ss.get('t_vs_zero',float('nan')):+.4f} |")
    L.append("")

    # ---- Phase 3 section ----
    L.append("## 3. Phase 3 — filter performance on OMEN trade log (BOTH ARMS)")
    L.append("")
    L.append("Per spec: report v2 filter on (full OMEN) AND (OMEN-minus-SL, "
             "i.e. trades excluding `SHORT_long` cell). Subsets: all / confirmed / rejected.")
    L.append("")
    L.append("| arm | sample | subset | N | win | mean $ | sum $ | Sharpe | max DD |")
    L.append("|---|---|---|---:|---:|---:|---:|---:|---:|")
    for arm in ("full_omen", "omen_minus_sl"):
        for samp in ("IS", "OOS", "Combined"):
            for subs in ("all", "confirmed", "rejected"):
                r = p3[(p3["arm"] == arm) & (p3["sample"] == samp)
                        & (p3["subset"] == subs)].iloc[0]
                wr = f"{r['win_rate']*100:.1f}%" if pd.notna(r["win_rate"]) else "—"
                sh = f"{r['sharpe']:+.2f}" if pd.notna(r["sharpe"]) else "—"
                L.append(f"| {arm} | {samp} | {subs} | {int(r['n'])} | {wr} | "
                         f"${r['mean']:+.2f} | ${r['sum']:+.0f} | {sh} | "
                         f"${r['max_dd']:+.0f} |")
    L.append("")

    # ---- Interpretation ----
    L.append("## 4. Honest interpretation")
    L.append("")
    L.append("**These results were generated on data the parameters were chosen from. ")
    L.append("Positive findings here are consistent with selection bias and do not ")
    L.append("constitute validation.**")
    L.append("")
    L.append("**Any deployment decision based on these results would be acting on ")
    L.append("consumed-data findings without forward-test validation.**")
    L.append("")
    L.append("**The post-mortem already established that TRCB framework signals decay ")
    L.append("by minute 15. Phase 3 results showing OMEN improvement on 25-min hold ")
    L.append("should be viewed with skepticism given the mechanism conflict.**")
    L.append("")
    L.append("### What the numbers actually show")
    L.append("")

    # Pull Phase 3 highlights
    def _row(arm, samp, subs):
        return p3[(p3["arm"] == arm) & (p3["sample"] == samp)
                   & (p3["subset"] == subs)].iloc[0]
    full_is_all = _row("full_omen", "IS", "all")
    full_is_conf = _row("full_omen", "IS", "confirmed")
    full_oos_all = _row("full_omen", "OOS", "all")
    full_oos_conf = _row("full_omen", "OOS", "confirmed")
    sl_oos_all = _row("omen_minus_sl", "OOS", "all")
    sl_oos_conf = _row("omen_minus_sl", "OOS", "confirmed")

    L.append("**Phase 2 (population) shows a strong-looking signal at every horizon:**")
    for h in FORWARD_HORIZONS_MIN:
        s = horizon_stats[h]["trig"]
        L.append(f"- {h}-min: n={s.get('n',0)}, mean={s.get('mean',0):+.2f} pts, "
                 f"t={s.get('t_vs_zero',0):+.2f}, %>0={s.get('pct_positive',0)*100:.1f}%")
    L.append("")
    L.append("This separation is exactly what one would expect from in-sample tuning. ")
    L.append("Selecting parameters that maximised forward signal in the post-mortem and ")
    L.append("then measuring forward signal at those parameters on the same data is ")
    L.append("a tautology, not a validation.")
    L.append("")
    L.append("**Phase 3 (OMEN trade log) shows a much weaker filter effect:**")
    L.append(f"- v2 fires on **{int(full_is_conf['n']) + int(full_oos_conf['n'])} / 332** "
             f"trades total (IS: {int(full_is_conf['n'])} / 174, OOS: "
             f"{int(full_oos_conf['n'])} / 158).")
    L.append(f"- full_omen IS: confirmed Sharpe = **{full_is_conf['sharpe']:+.2f}** vs "
             f"all-IS Sharpe = **{full_is_all['sharpe']:+.2f}**. Confirmed is *worse* "
             "on a Sharpe basis despite higher mean per-trade $.")
    L.append(f"- full_omen OOS: only 1 confirmed trade (n=1 → Sharpe undefined). "
             "No useful signal from the filter at OOS scale.")
    sl_conf_sh = (f"{sl_oos_conf['sharpe']:+.2f}"
                  if pd.notna(sl_oos_conf['sharpe']) else "undefined (n=1)")
    L.append(f"- omen_minus_sl OOS: all-Sharpe = {sl_oos_all['sharpe']:+.2f}, ")
    L.append(f"  confirmed-Sharpe = {sl_conf_sh}.")
    L.append("")
    L.append("**The two arms (full vs minus-SL) tell almost the same filter story** ")
    L.append("because the SL exclusion happens BEFORE the filter is applied. The ")
    L.append("filter's discriminative power within either arm is statistically ")
    L.append("indistinguishable from random selection at these N's.")
    L.append("")
    L.append("**Mechanism conflict the post-mortem already flagged:** the prior Q4 ")
    L.append("MFE/MAE analysis on the 27 v1 triggers showed RUN_UP_THEN_FADE as the ")
    L.append("modal shape and median time-to-MFE ≈ 7 min. If v2 inherits the same ")
    L.append("structural property, a 25-min hold systematically gives back favorable ")
    L.append("excursion — meaning a v2-filtered OMEN with the locked 25-min time stop ")
    L.append("would inherit the same mismatched-exit problem.")
    L.append("")

    # ---- Section 5: pre-reg comparison ----
    L.append("## 5. What this test cannot answer that a forward test could")
    L.append("")
    L.append("**This test can answer:**")
    L.append("- Whether 30s/1.5:1 produces more triggers than 60s/2.0:1 on this corpus → yes.")
    L.append("- Whether triggered bars in this corpus have favorable forward-return mean → yes.")
    L.append("- Whether the v2 filter fires on the OMEN trade log in this corpus → rarely (2.1%).")
    L.append("")
    L.append("**This test cannot answer:**")
    L.append("- Whether the apparent edge replicates on data not used to choose parameters.")
    L.append("- Whether the 1.5:1 ratio is the right threshold for 30s windows in general.")
    L.append("- Whether the strong t-stats at 1m/5m horizons reflect a genuine impulse ")
    L.append("  or a quirk of this corpus's price-microstructure regime.")
    L.append("- Whether a forward-only sample would show the same per-direction balance ")
    L.append("  (long mean ≈ short mean) seen here.")
    L.append("")
    L.append("### Sample size needed for a forward-only validation")
    L.append("")
    L.append("Power calculation rough sketch (informative only — not a pre-reg):")
    L.append("- Population-trigger rate of ~4.4% means ~3.4 triggers per evaluable session.")
    L.append(f"- The observed v2 25-min mean is {horizon_stats[25]['trig'].get('mean', float('nan')):+.2f} pts, std "
             f"{horizon_stats[25]['trig'].get('std', float('nan')):.2f} pts.")
    L.append(f"- Effect size d ≈ "
             f"{(horizon_stats[25]['trig'].get('mean', 0) / max(horizon_stats[25]['trig'].get('std', 1), 1e-9)):.3f}. ")
    L.append("- For ~80% power at α=0.05 (one-sided) to detect that effect, n ≈ 70-100 ")
    L.append("  triggers needed → roughly 20-30 fresh trading sessions if the corpus ")
    L.append("  produces 3.4 triggers per session and the effect size is real.")
    L.append("- For Phase-3-level claims on OMEN trade log, much more: with v2 firing on ")
    L.append("  ~2% of OMEN entries, 30-50 sessions of fresh data would yield only ")
    L.append("  ~3-5 v2-confirmed OMEN trades — insufficient. To test the FILTER on ")
    L.append("  OMEN's actual signal cadence would require **hundreds** of fresh ")
    L.append("  sessions, not a few weeks.")
    L.append("")
    L.append("### Recommendation")
    L.append("")
    L.append("Treat these Phase 2 / Phase 3 numbers as descriptive of a tuned ")
    L.append("parameter set on consumed data. No deployment action. If TRCB-v2 is ")
    L.append("genuinely a candidate, lock 30s/1.5 today, and only collect forward ")
    L.append("data **with no further parameter changes**. The v2 filter's apparent ")
    L.append("low fire rate on OMEN trades suggests it is unlikely to be useful as ")
    L.append("a confirmation filter for OMEN's signal in its current form.")
    L.append("")

    SYNTHESIS_MD.write_text("\n".join(L) + "\n")
    print(f"Saved SYNTHESIS report: {SYNTHESIS_MD}")


if __name__ == "__main__":
    main()
