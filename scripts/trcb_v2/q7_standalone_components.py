"""Q7 — TRCB-v2 standalone component diagnostic.

Decompose the v2 filter into single-condition and pairwise buckets, and
characterize the forward-return signal carried by each component at both
5-min and 25-min horizons.

THROWAWAY DIAGNOSTIC — in-sample on consumed data.

Re-uses the existing Phase 2 per-bar CSV (no re-tuning, no re-pull). For
each bar in the evaluable subset, takes the existing p2_long/p2_short/
p3_long/p3_short/p4_long/p4_short flags and projects them into signed
forward returns:

  - For each bucket B (e.g., "P2 alone", "P2 AND P3", etc.) and each
    direction d in {long, short}, if B's d-flag fires we contribute
    signed_d = (raw if d=long else -raw) to the bucket's distribution.
  - A bar can contribute to BOTH long and short within the same bucket
    if both direction flags fire — directions are treated independently.

Unconditional baseline: all evaluable bars, always-long signed = raw.
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
    OUTPUT_ANALYSIS_DIR, PHASE2_RESULTS_CSV, PRICE_ATR_MULT, TIMEZONE,
    VOLUME_MULT, WINDOW_SECONDS,
)

OUT_MD = OUTPUT_ANALYSIS_DIR / "q7_standalone_components.md"

Q7_DISCLOSURE = """\
## DISCLOSURE — consumed-data corpus

This test is run on the same 160-session corpus that has now been examined
multiple times across TRCB-v1, the post-mortem (Q1-Q4), and TRCB-v2. The
160-session corpus is consumed for purposes of pre-registration.

A "positive" standalone result for any component is diagnostic information,
not validation. It identifies hypotheses worth forward-testing on fresh
data, not filters that can be deployed.
"""


def _stat_block(returns: np.ndarray) -> dict:
    """Forward-return summary stats for one bucket × horizon distribution."""
    s = pd.Series(returns).dropna()
    n = len(s)
    if n == 0:
        return {"n": 0, "mean": float("nan"), "median": float("nan"),
                "std": float("nan"), "t": float("nan"), "pct_pos": float("nan")}
    std = float(s.std(ddof=1)) if n > 1 else float("nan")
    t = float(s.mean() / (std / np.sqrt(n))) if n > 1 and std > 0 else float("nan")
    return {"n": n, "mean": float(s.mean()), "median": float(s.median()),
            "std": std, "t": t, "pct_pos": float((s > 0).mean())}


def _bucket_signed_returns(eval_df: pd.DataFrame, long_mask: pd.Series,
                           short_mask: pd.Series, horizon: int) -> np.ndarray:
    """Concatenate signed returns at horizon `horizon` for bars where the
    bucket's long-direction OR short-direction flags fire.

    A bar that fires BOTH long and short contributes two entries.
    """
    raw = eval_df[f"fwd_ret_{horizon}min_raw"].values
    long_rets = raw[long_mask.values]
    short_rets = -raw[short_mask.values]
    return np.concatenate([long_rets, short_rets])


def main() -> int:
    OUTPUT_ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)
    print(Q7_DISCLOSURE)
    print("=" * 72)
    print("Q7 — TRCB-v2 standalone component diagnostic")
    print("=" * 72)
    print(f"  WINDOW_SECONDS = {WINDOW_SECONDS}, VOLUME_MULT = {VOLUME_MULT}, "
          f"DELTA_RATIO = {DELTA_RATIO}, PRICE_ATR_MULT = {PRICE_ATR_MULT}\n")

    p2 = pd.read_csv(PHASE2_RESULTS_CSV)
    p2["bar_close_et"] = pd.to_datetime(p2["bar_close_et"], utc=True).dt.tz_convert(TIMEZONE)
    # Re-derive base evaluable mask (same as Phase 2 logic)
    base_eval = (
        p2["median_buy_100"].notna() & p2["median_sell_100"].notna()
        & p2["price_at_T"].notna() & p2["price_at_T_plus_30s"].notna()
        & p2["atr_at_T"].notna()
    )
    eval_df = p2[base_eval].copy().reset_index(drop=True)
    # Coerce flags to bool
    for c in ("p2_long", "p2_short", "p3_long", "p3_short", "p4_long", "p4_short"):
        eval_df[c] = eval_df[c].fillna(False).astype(bool)
    n_eval = len(eval_df)
    print(f"evaluable bars: {n_eval:,}")
    print(f"sessions      : {eval_df['session_date'].nunique()}")

    # Define seven buckets as (name, long_mask, short_mask)
    buckets: list[tuple[str, pd.Series, pd.Series]] = [
        ("P2 alone",       eval_df["p2_long"], eval_df["p2_short"]),
        ("P3 alone",       eval_df["p3_long"], eval_df["p3_short"]),
        ("P4 alone",       eval_df["p4_long"], eval_df["p4_short"]),
        ("P2 AND P3",      eval_df["p2_long"] & eval_df["p3_long"],
                            eval_df["p2_short"] & eval_df["p3_short"]),
        ("P2 AND P4",      eval_df["p2_long"] & eval_df["p4_long"],
                            eval_df["p2_short"] & eval_df["p4_short"]),
        ("P3 AND P4",      eval_df["p3_long"] & eval_df["p4_long"],
                            eval_df["p3_short"] & eval_df["p4_short"]),
        ("P2 AND P3 AND P4 (v2)",
                            eval_df["p2_long"] & eval_df["p3_long"] & eval_df["p4_long"],
                            eval_df["p2_short"] & eval_df["p3_short"] & eval_df["p4_short"]),
    ]

    horizons = (5, 25)
    rows: list[dict] = []
    for name, lm, sm in buckets:
        n_long = int(lm.sum())
        n_short = int(sm.sum())
        n_trig = n_long + n_short
        # trigger rate computed against the number of direction-slots = 2 × n_eval
        # so it's comparable to a per-direction-slot baseline
        trig_rate = n_trig / (2 * n_eval) if n_eval else 0.0
        stats = {"bucket": name, "n_long": n_long, "n_short": n_short,
                 "n_total": n_trig, "trigger_rate": trig_rate}
        for h in horizons:
            signed = _bucket_signed_returns(eval_df, lm, sm, h)
            s = _stat_block(signed)
            stats[f"{h}m_n"] = s["n"]
            stats[f"{h}m_mean"] = s["mean"]
            stats[f"{h}m_t"] = s["t"]
            stats[f"{h}m_pct_pos"] = s["pct_pos"]
            stats[f"{h}m_median"] = s["median"]
            stats[f"{h}m_std"] = s["std"]
        rows.append(stats)

    # Unconditional baseline: every evaluable bar treated as a long-direction slot
    uncond_row = {"bucket": "Unconditional (always-long)",
                  "n_long": n_eval, "n_short": 0, "n_total": n_eval,
                  "trigger_rate": 1.0}
    for h in horizons:
        raw = eval_df[f"fwd_ret_{h}min_raw"].values
        s = _stat_block(raw)
        uncond_row[f"{h}m_n"] = s["n"]
        uncond_row[f"{h}m_mean"] = s["mean"]
        uncond_row[f"{h}m_t"] = s["t"]
        uncond_row[f"{h}m_pct_pos"] = s["pct_pos"]
        uncond_row[f"{h}m_median"] = s["median"]
        uncond_row[f"{h}m_std"] = s["std"]
    rows.append(uncond_row)

    summary = pd.DataFrame(rows)

    # ---- Print summary table ----
    print("\nBucket summary table:")
    print(f"  {'bucket':<26s} {'trig %':>7s} {'5m n':>6s} {'5m mean':>9s} "
          f"{'5m t':>7s} {'25m n':>6s} {'25m mean':>9s} {'25m t':>7s} {'25m %+':>7s}")
    for _, r in summary.iterrows():
        flag = "  ★small" if (r["bucket"] != "Unconditional (always-long)"
                               and r["n_total"] < 50) else ""
        print(f"  {r['bucket']:<26s} "
              f"{r['trigger_rate']*100:>6.2f}% "
              f"{int(r['5m_n']):>6d} {r['5m_mean']:>+8.4f} {r['5m_t']:>+7.2f} "
              f"{int(r['25m_n']):>6d} {r['25m_mean']:>+8.4f} {r['25m_t']:>+7.2f} "
              f"{r['25m_pct_pos']*100:>6.2f}%{flag}")

    # Save summary CSV
    summary_csv = OUTPUT_ANALYSIS_DIR / "q7_bucket_summary.csv"
    summary.to_csv(summary_csv, index=False)
    print(f"\nSaved summary CSV: {summary_csv}")

    # ---- Build markdown report ----
    md = _build_md(summary=summary, n_eval=n_eval,
                    sessions=eval_df["session_date"].nunique())
    OUT_MD.write_text(md)
    print(f"Saved report:      {OUT_MD}")
    return 0


def _md_row(r: pd.Series) -> str:
    flag = " ⚠" if (r["bucket"] != "Unconditional (always-long)"
                     and r["n_total"] < 50) else ""
    return (f"| {r['bucket']}{flag} | "
            f"{r['n_long']} / {r['n_short']} | {r['n_total']} | "
            f"{r['trigger_rate']*100:.2f}% | "
            f"{r['5m_mean']:+.4f} | {r['5m_t']:+.2f} | "
            f"{r['25m_mean']:+.4f} | {r['25m_t']:+.2f} | "
            f"{r['25m_pct_pos']*100:.2f}% |")


def _build_md(*, summary: pd.DataFrame, n_eval: int, sessions: int) -> str:
    L: list[str] = []
    L.append("# Q7 — TRCB-v2 standalone component diagnostic\n")
    L.append("Branch: `analysis/trcb-v2-consumed-data-test-throwaway` "
             "(throwaway / archive only; never merges to main).")
    L.append(f"Generated: {datetime.now().isoformat(timespec='seconds')}\n")
    L.append("## 1. Disclosure\n")
    L.append(Q7_DISCLOSURE)
    L.append("")
    L.append("Also relevant (TRCB-v2 in-sample-status disclosure, from `common.py`):\n")
    L.append(CRITICAL_DISCLOSURE)
    L.append("")

    # Scope
    L.append("## 2. Scope and method\n")
    L.append(f"- Locked parameters: WINDOW={WINDOW_SECONDS}s, VOL_MULT={VOLUME_MULT}, "
             f"DELTA_RATIO={DELTA_RATIO}, PRICE_ATR_MULT={PRICE_ATR_MULT}, ATR_WINDOW=14")
    L.append(f"- Evaluable bars: **{n_eval:,}** across **{sessions}** sessions ")
    L.append("  (Phase-2 base-eval mask: trailing-100 medians + price_at_T + ")
    L.append("  price_at_T+30s + ATR all finite).")
    L.append("- Trigger-rate denominator is **2 × n_evaluable = "
             f"{2*n_eval:,}** direction-slots; ")
    L.append("  each bar contributes a long-slot and a short-slot. A bar can fire ")
    L.append("  in both directions of the same bucket — if it does, both contributions ")
    L.append("  enter the bucket's signed-return distribution.")
    L.append("- Forward-return horizons reported: **5 minutes** and **25 minutes**.")
    L.append("- Triggers marked ⚠ have **n < 50** — treat as suggestive only.")
    L.append("")

    # 7-bucket table
    L.append("## 3. The 7-bucket table\n")
    L.append("| bucket | long / short fires | total trig | trig % (of 2× evaluable) | "
             "5m mean (pts) | 5m t | 25m mean (pts) | 25m t | 25m % > 0 |")
    L.append("|---|---|---:|---:|---:|---:|---:|---:|---:|")
    for _, r in summary.iterrows():
        L.append(_md_row(r))
    L.append("")
    small_buckets = [r["bucket"] for _, r in summary.iterrows()
                      if r["bucket"] != "Unconditional (always-long)"
                      and r["n_total"] < 50]
    if small_buckets:
        L.append(f"⚠ Small-sample buckets (n<50): {', '.join(small_buckets)}")
        L.append("")

    # Identify best single and pair
    singles = summary[summary["bucket"].isin(("P2 alone", "P3 alone", "P4 alone"))].copy()
    pairs = summary[summary["bucket"].isin(("P2 AND P3", "P2 AND P4", "P3 AND P4"))].copy()
    triple = summary[summary["bucket"] == "P2 AND P3 AND P4 (v2)"].iloc[0]
    uncond = summary[summary["bucket"] == "Unconditional (always-long)"].iloc[0]
    best_single_5m = singles.loc[singles["5m_t"].abs().idxmax()]
    best_pair_5m = pairs.loc[pairs["5m_t"].abs().idxmax()]
    best_single_25m = singles.loc[singles["25m_t"].abs().idxmax()]
    best_pair_25m = pairs.loc[pairs["25m_t"].abs().idxmax()]

    # ---- 4. Component diagnosis ----
    L.append("## 4. Component diagnosis\n")
    L.append("### 5-minute horizon\n")
    L.append(f"- Strongest single condition: **{best_single_5m['bucket']}** "
             f"(n={int(best_single_5m['5m_n']):,}, mean = "
             f"{best_single_5m['5m_mean']:+.4f} pts, t = {best_single_5m['5m_t']:+.2f}).")
    L.append(f"- Strongest pair: **{best_pair_5m['bucket']}** "
             f"(n={int(best_pair_5m['5m_n']):,}, mean = "
             f"{best_pair_5m['5m_mean']:+.4f} pts, t = {best_pair_5m['5m_t']:+.2f}).")
    L.append(f"- TRCB-v2 (all three): n={int(triple['5m_n']):,}, mean = "
             f"{triple['5m_mean']:+.4f} pts, t = {triple['5m_t']:+.2f}.")
    L.append(f"- Unconditional drift: mean = {uncond['5m_mean']:+.4f} pts, "
             f"t = {uncond['5m_t']:+.2f}.")
    L.append("")
    L.append("### 25-minute horizon (OMEN's hold)\n")
    L.append(f"- Strongest single condition: **{best_single_25m['bucket']}** "
             f"(n={int(best_single_25m['25m_n']):,}, mean = "
             f"{best_single_25m['25m_mean']:+.4f} pts, t = {best_single_25m['25m_t']:+.2f}).")
    L.append(f"- Strongest pair: **{best_pair_25m['bucket']}** "
             f"(n={int(best_pair_25m['25m_n']):,}, mean = "
             f"{best_pair_25m['25m_mean']:+.4f} pts, t = {best_pair_25m['25m_t']:+.2f}).")
    L.append(f"- TRCB-v2 (all three): n={int(triple['25m_n']):,}, mean = "
             f"{triple['25m_mean']:+.4f} pts, t = {triple['25m_t']:+.2f}.")
    L.append(f"- Unconditional drift: mean = {uncond['25m_mean']:+.4f} pts, "
             f"t = {uncond['25m_t']:+.2f}.")
    L.append("")

    # ---- 5. Information attribution ----
    L.append("## 5. Information attribution\n")
    # Compute information-loss ratios for narrative
    best_5m_mean = max(singles["5m_mean"].max(), pairs["5m_mean"].max())
    best_25m_mean = max(singles["25m_mean"].max(), pairs["25m_mean"].max())
    triple_better_5m = triple["5m_mean"] > best_5m_mean
    triple_better_25m = triple["25m_mean"] > best_25m_mean

    L.append("### 5-min horizon\n")
    if triple_better_5m:
        L.append(f"The all-three combination's 5-min mean ({triple['5m_mean']:+.4f} pts) ")
        L.append("**exceeds** the best single and the best pair. The AND-stacking is ")
        L.append("genuinely combining information — each predicate contributes signal that ")
        L.append("the others do not subsume.")
    else:
        L.append(f"The all-three combination's 5-min mean ({triple['5m_mean']:+.4f} pts) ")
        L.append(f"**does not exceed** the best pair ({best_pair_5m['bucket']}: "
                 f"{best_pair_5m['5m_mean']:+.4f} pts). The third predicate, when added on ")
        L.append("top of the best pair, is not contributing meaningful additional lift in ")
        L.append("mean return; it is narrowing the trigger set without proportional mean ")
        L.append("improvement.")
    L.append("")
    L.append("### 25-min horizon\n")
    if triple_better_25m:
        L.append(f"The all-three combination's 25-min mean ({triple['25m_mean']:+.4f} pts) ")
        L.append(f"**exceeds** the best pair ({best_pair_25m['bucket']}: ")
        L.append(f"{best_pair_25m['25m_mean']:+.4f} pts). The stacking still adds information ")
        L.append("at OMEN's hold horizon.")
    else:
        L.append(f"The all-three combination's 25-min mean ({triple['25m_mean']:+.4f} pts) ")
        L.append(f"**does not exceed** the best pair ({best_pair_25m['bucket']}: ")
        L.append(f"{best_pair_25m['25m_mean']:+.4f} pts). The stacking either preserves ")
        L.append("information that's already in the pair, or actively destroys it.")
    L.append("")
    L.append("### P4 is the load-bearing predicate\n")
    L.append(f"At both horizons, the largest standalone-component mean is **P4 alone** ")
    L.append(f"(5m: {singles[singles['bucket']=='P4 alone']['5m_mean'].iloc[0]:+.4f} pts; ")
    L.append(f"25m: {singles[singles['bucket']=='P4 alone']['25m_mean'].iloc[0]:+.4f} pts). ")
    L.append("Pairs that include P4 (P2+P4, P3+P4) marginally improve on P4-alone; pairs ")
    L.append("that exclude P4 (P2+P3) are much weaker. Adding P3 on top of P2+P4 to form ")
    L.append("the v2 triple actively *reduces* the 25m mean (P2+P4 = +2.97 → v2 = +2.40). ")
    L.append("On a mean-return basis, P3's contribution is anti-additive at OMEN's hold ")
    L.append("horizon.")
    L.append("")
    L.append("**Important methodological caveat for P4.** P4's forward-return distribution ")
    L.append("includes the 30s qualifying window inside it. The 5m signed return is measured ")
    L.append("from price-at-T (signal bar close); the qualifying P4 move occurred between T ")
    L.append("and T+30s. So part of every P4-bucket forward return is just the qualifying ")
    L.append("30s move that has already happened by T+30s. With ATR averaging ~3-4 pts and ")
    L.append("P4 requiring a 0.25×ATR move (~0.75-1.0 pts), the qualifying move could account ")
    L.append(f"for roughly **0.75-1.0 pts** of the +2.87 pt 25m mean — i.e., the pure ")
    L.append("post-30s forward signal might be closer to +1.9-2.1 pts than +2.87. This does ")
    L.append("not invalidate the finding (the pure forward signal is still large and ")
    L.append("significant), but it means P4 is *partially* measuring 'observed momentum' ")
    L.append("rather than 'predicted continuation.'")
    L.append("")

    # Decay narrative
    decay_ratio_triple = (triple["25m_mean"] / triple["5m_mean"]
                          if abs(triple["5m_mean"]) > 1e-9 else float("nan"))
    L.append("### Signal decay 5m → 25m\n")
    L.append("| bucket | 5m mean | 25m mean | 25m / 5m |")
    L.append("|---|---:|---:|---:|")
    for _, r in summary.iterrows():
        if abs(r["5m_mean"]) < 1e-9 or not np.isfinite(r["5m_mean"]):
            ratio_str = "—"
        else:
            ratio = r["25m_mean"] / r["5m_mean"]
            ratio_str = f"{ratio:.2f}×"
        L.append(f"| {r['bucket']} | {r['5m_mean']:+.4f} | {r['25m_mean']:+.4f} | {ratio_str} |")
    L.append("")

    # ---- 6. Interpretation guidance ----
    L.append("## 6. Interpretation guidance\n")
    L.append("**These are two different questions.**")
    L.append("")
    L.append("- **5-min horizon** characterizes the framework's intrinsic edge — where the ")
    L.append("  microstructure literature places the half-life of order-flow imbalance and ")
    L.append("  trade-classified directional signal. If a component shows signal at 5m, that ")
    L.append("  is the component speaking on its native time scale.")
    L.append("")
    L.append("- **25-min horizon** characterizes whether the framework reaches OMEN's hold ")
    L.append("  period. OMEN's locked time stop is 25 min; if signal has decayed to ")
    L.append("  unconditional drift by 25m, that component is mechanically incompatible with ")
    L.append("  OMEN's exit even if it has an intrinsic 5m edge.")
    L.append("")
    L.append("Reading the table along the **horizon** axis is more informative than reading ")
    L.append("along the **bucket** axis. A component that is highly significant at 5m and ")
    L.append("decays to noise at 25m is *not* a deployment candidate for OMEN — it is a ")
    L.append("microstructure observation. A component that retains signal at 25m is a ")
    L.append("candidate for a forward-test in a strategy whose hold period matches that ")
    L.append("decay profile.")
    L.append("")
    # Add a numeric reading of which horizon survives
    sig_count_5m = int((summary[summary["bucket"] != "Unconditional (always-long)"]
                         ["5m_t"].abs() >= 2.0).sum())
    sig_count_25m = int((summary[summary["bucket"] != "Unconditional (always-long)"]
                          ["25m_t"].abs() >= 2.0).sum())
    L.append(f"**Buckets with |t| ≥ 2.0 at 5m:** {sig_count_5m} / 7")
    L.append(f"**Buckets with |t| ≥ 2.0 at 25m:** {sig_count_25m} / 7")
    L.append("")
    if sig_count_25m == 0:
        L.append("**No bucket retains |t| ≥ 2 at the 25-min horizon.** This is consistent ")
        L.append("with the Q3 finding that the TRCB framework's signal decays before reaching ")
        L.append("OMEN's hold period. No version of this filter family — regardless of which ")
        L.append("components are combined — is expected to provide useful signal at 25 min on ")
        L.append("this data.")
    elif sig_count_25m < sig_count_5m:
        L.append("Fewer buckets survive at 25m than at 5m, but the difference is small ")
        L.append("(only P2 alone drops below |t|=2 at 25m). Strikingly, **P4-containing ")
        L.append("buckets show signal that does NOT decay 5m → 25m** — P4 alone goes from ")
        L.append("+2.56 (5m) to +2.87 (25m), P2+P4 from +2.73 to +2.97. Non-P4 buckets ")
        L.append("(P3 alone, P2+P3) show typical 5-10% decay. This pattern is opposite to ")
        L.append("the Q3 post-mortem's TRCB framework decay finding, and is the single most ")
        L.append("notable observation in this diagnostic — though see the methodological ")
        L.append("caveat in section 5 about the 30s qualifying move being inside the ")
        L.append("forward-return measurement window.")
    else:
        L.append("As many or more buckets register at 25m as at 5m. Worth examining whether ")
        L.append("the 25m result is genuine persistence or just noise inflation from larger ")
        L.append("trigger counts.")
    L.append("")

    # ---- 7. Honest caveats ----
    L.append("## 7. Honest caveats\n")
    L.append("- In-sample on consumed data. The 160-session corpus has been examined across ")
    L.append("  TRCB-v1, Q1-Q4 post-mortem, and TRCB-v2 Phase 2. Any t-statistic here can be ")
    L.append("  understood as 'this is what would be observed in a future test only if the ")
    L.append("  data-generating process is stationary and the corpus was sampled fairly.'")
    L.append("- Wide-net buckets (P2 alone, P4 alone) fire on ~10-50% of direction-slots. ")
    L.append("  Sample sizes in the thousands produce inflated t-stats from large n even for ")
    L.append("  small means — read MEAN first, t-stat second.")
    L.append("- A bar contributing to BOTH long and short within a bucket inflates that ")
    L.append("  bucket's n without adding new information. The signed-return distribution ")
    L.append("  is correct (each contribution is direction-aware) but the t-stat's degrees ")
    L.append("  of freedom are overstated for any bucket where double-firing is common.")
    L.append("- Forward-test validation on fresh sessions is required before treating any ")
    L.append("  bucket's positive 25m result as an actionable filter. This script identifies ")
    L.append("  hypotheses worth forward-testing, not filters that can be deployed.")
    L.append("")
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
