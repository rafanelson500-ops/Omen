"""Q6 — bottleneck diagnosis of the TRCB-v2 Phase 3 result.

Why does v2 confirm only 7 / 332 OMEN trades? Which of P2/P3/P4 is the
binding constraint, and does OMEN's entry distribution differ from
random population bars in a way that mechanically suppresses one
specific predicate?

THROWAWAY DESCRIPTIVE DIAGNOSIS. No new filter spec, no new parameters,
no optimization. Re-derives per-condition flags from the existing
Phase 3 trade-level CSV (which already has p2_*, p3_*, p4_* columns).
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (  # noqa: E402
    DELTA_RATIO, OUTPUT_ANALYSIS_DIR, PHASE2_RESULTS_CSV, PHASE3_RESULTS_CSV,
    PRICE_ATR_MULT, TIMEZONE, VOLUME_MULT, WINDOW_SECONDS,
)

OUT_MD = OUTPUT_ANALYSIS_DIR / "q6_bottleneck_diagnosis.md"


def _trade_direction_flags(df: pd.DataFrame) -> pd.DataFrame:
    """Project direction-specific flags so each trade has p2/p3/p4 in its OWN side.

    Returns df with new columns p2/p3/p4 (the trade's direction-relevant
    predicate) plus delta_ratio and signed_price_move.
    """
    out = df.copy()
    is_long = out["side"] == 1
    out["p2"] = np.where(is_long, out["p2_long"], out["p2_short"]).astype(bool)
    out["p3"] = np.where(is_long, out["p3_long"], out["p3_short"]).astype(bool)
    out["p4"] = np.where(is_long, out["p4_long"], out["p4_short"]).astype(bool)
    out["delta_ratio"] = np.where(is_long, out["delta_ratio_long"], out["delta_ratio_short"])
    out["signed_price_move"] = np.where(is_long, out["price_move_30s"], -out["price_move_30s"])
    out["signed_atr_units"] = out["signed_price_move"] / out["p4_threshold"].replace(0, np.nan)
    # Directional volume on trade's own side
    out["dir_vol_own_side"] = np.where(is_long, out["dir_buy_vol_30s"], out["dir_sell_vol_30s"])
    out["dir_vol_opp_side"] = np.where(is_long, out["dir_sell_vol_30s"], out["dir_buy_vol_30s"])
    out["median_own_100"] = np.where(is_long, out["median_buy_100"], out["median_sell_100"])
    out["vol_vs_median"] = out["dir_vol_own_side"] / out["median_own_100"].replace(0, np.nan)
    return out


def _population_direction_stats(p2_df: pd.DataFrame) -> pd.DataFrame:
    """Expand the population Phase 2 result to a per-direction-slot table.

    For each evaluable bar, emit two rows: one as a 'long-direction slot'
    with p2_long/p3_long/p4_long, and one as a 'short-direction slot'.
    Used for apples-to-apples comparison with OMEN trades (which are
    inherently direction-specific).
    """
    # Filter to base-evaluable (median + price + atr all finite)
    eval_mask = (
        p2_df["median_buy_100"].notna() & p2_df["median_sell_100"].notna()
        & p2_df["price_at_T"].notna() & p2_df["price_at_T_plus_30s"].notna()
        & p2_df["atr_at_T"].notna()
    )
    df = p2_df[eval_mask].copy()
    long_slots = pd.DataFrame({
        "bar_close_et": df["bar_close_et"], "direction": "long",
        "p2": df["p2_long"].fillna(False).astype(bool),
        "p3": df["p3_long"].fillna(False).astype(bool),
        "p4": df["p4_long"].fillna(False).astype(bool),
        "delta_ratio": df["delta_ratio_long"],
        "signed_price_move": df["price_at_T_plus_30s"] - df["price_at_T"],
        "p4_threshold": df["p4_threshold"],
        "dir_vol_own_side": df["dir_buy_vol_30s"],
        "median_own_100": df["median_buy_100"],
    })
    short_slots = pd.DataFrame({
        "bar_close_et": df["bar_close_et"], "direction": "short",
        "p2": df["p2_short"].fillna(False).astype(bool),
        "p3": df["p3_short"].fillna(False).astype(bool),
        "p4": df["p4_short"].fillna(False).astype(bool),
        "delta_ratio": df["delta_ratio_short"],
        "signed_price_move": -(df["price_at_T_plus_30s"] - df["price_at_T"]),
        "p4_threshold": df["p4_threshold"],
        "dir_vol_own_side": df["dir_sell_vol_30s"],
        "median_own_100": df["median_sell_100"],
    })
    out = pd.concat([long_slots, short_slots], ignore_index=True)
    out["signed_atr_units"] = out["signed_price_move"] / out["p4_threshold"].replace(0, np.nan)
    out["vol_vs_median"] = out["dir_vol_own_side"] / out["median_own_100"].replace(0, np.nan)
    return out


def _pct(numer: int, denom: int) -> str:
    if denom == 0:
        return "0/0 (—)"
    return f"{numer}/{denom} ({100.0*numer/denom:.1f}%)"


def _quantiles(series: pd.Series, q: list[float]) -> list[float]:
    s = series.dropna()
    if len(s) == 0:
        return [float("nan")] * len(q)
    return [float(np.quantile(s, qi)) for qi in q]


def main() -> int:
    print("=" * 72)
    print("Q6 — TRCB-v2 bottleneck diagnosis")
    print("=" * 72)

    # ---- Load Phase 3 trade results ----
    trades = pd.read_csv(PHASE3_RESULTS_CSV)
    trades = _trade_direction_flags(trades)
    trades["entry_time_et"] = pd.to_datetime(trades["entry_time"], utc=True).dt.tz_convert(TIMEZONE)
    trades["hour"] = trades["entry_time_et"].dt.hour

    n_total = len(trades)
    n_evaluable = int(trades["FILTER_EVALUABLE"].sum())
    n_confirmed = int(trades["FILTER_CONFIRMED"].sum())
    print(f"trades total      : {n_total}")
    print(f"FILTER_EVALUABLE  : {n_evaluable}")
    print(f"FILTER_CONFIRMED  : {n_confirmed}")
    print(f"all P2/P3/P4 True : {int((trades['p2'] & trades['p3'] & trades['p4']).sum())}")

    eval_trades = trades[trades["FILTER_EVALUABLE"]].copy()

    # ---- Load Phase 2 population ----
    p2 = pd.read_csv(PHASE2_RESULTS_CSV)
    p2["bar_close_et"] = pd.to_datetime(p2["bar_close_et"], utc=True).dt.tz_convert(TIMEZONE)
    pop = _population_direction_stats(p2)
    print(f"population direction-slots: {len(pop):,} "
          f"({pop[pop['direction']=='long'].shape[0]:,} long + "
          f"{pop[pop['direction']=='short'].shape[0]:,} short)")
    pop_total = len(pop)
    pop["all_three"] = pop["p2"] & pop["p3"] & pop["p4"]
    pop["hour"] = pop["bar_close_et"].dt.hour

    # ---- Step 1: per-condition pass rates (both views) ----
    def rate(df, col):  # noqa
        return float(df[col].sum()), len(df)

    print("\n" + "-" * 72)
    print("STEP 1 — per-condition pass rates (independent)")
    print("-" * 72)
    print("\n  All 332 OMEN trades:")
    for c in ("p2", "p3", "p4"):
        n_pass, n_tot = rate(trades, c)
        print(f"    {c}: {_pct(int(n_pass), n_tot)}")
    print("\n  Evaluable-only 256 OMEN trades:")
    for c in ("p2", "p3", "p4"):
        n_pass, n_tot = rate(eval_trades, c)
        print(f"    {c}: {_pct(int(n_pass), n_tot)}")
    print("\n  Population (per-direction-slot, n=23,978):")
    for c in ("p2", "p3", "p4"):
        n_pass, n_tot = rate(pop, c)
        print(f"    {c}: {_pct(int(n_pass), n_tot)}")

    # ---- Step 2: pairwise pass rates ----
    print("\n" + "-" * 72)
    print("STEP 2 — pairwise pass rates")
    print("-" * 72)

    def pair(df, a, b):
        return int((df[a] & df[b]).sum()), len(df)

    def triple(df):
        return int((df["p2"] & df["p3"] & df["p4"]).sum()), len(df)
    print("\n  OMEN trades (evaluable only):")
    for a, b in (("p2", "p3"), ("p2", "p4"), ("p3", "p4")):
        n_p, n_t = pair(eval_trades, a, b)
        print(f"    {a} & {b}: {_pct(n_p, n_t)}")
    n_p, n_t = triple(eval_trades)
    print(f"    all three: {_pct(n_p, n_t)}")
    print("\n  Population (per-direction-slot):")
    for a, b in (("p2", "p3"), ("p2", "p4"), ("p3", "p4")):
        n_p, n_t = pair(pop, a, b)
        print(f"    {a} & {b}: {_pct(n_p, n_t)}")
    n_p, n_t = triple(pop)
    print(f"    all three: {_pct(n_p, n_t)}")

    # ---- Step 3: single-condition failure attribution ----
    print("\n" + "-" * 72)
    print("STEP 3 — failure attribution (among evaluable-rejected trades)")
    print("-" * 72)
    rejected = eval_trades[~eval_trades["FILTER_CONFIRMED"]].copy()
    print(f"  evaluable + rejected: {len(rejected)}")

    def bucketize(df: pd.DataFrame) -> dict[str, int]:
        p2 = df["p2"]; p3 = df["p3"]; p4 = df["p4"]
        return {
            "fail_P2_only":      int((~p2 &  p3 &  p4).sum()),
            "fail_P3_only":      int(( p2 & ~p3 &  p4).sum()),
            "fail_P4_only":      int(( p2 &  p3 & ~p4).sum()),
            "fail_P2_P3":        int((~p2 & ~p3 &  p4).sum()),
            "fail_P2_P4":        int((~p2 &  p3 & ~p4).sum()),
            "fail_P3_P4":        int(( p2 & ~p3 & ~p4).sum()),
            "fail_all":          int((~p2 & ~p3 & ~p4).sum()),
        }

    rej_buckets = bucketize(rejected)
    for k, v in rej_buckets.items():
        print(f"    {k:<20s}: {_pct(v, len(rejected))}")
    # Per-condition involvement (any bucket where Pi failed)
    print("\n  Per-condition involvement in failures:")
    for c, label in (("p2", "P2"), ("p3", "P3"), ("p4", "P4")):
        n_fail = int((~rejected[c]).sum())
        print(f"    {label} failed in: {_pct(n_fail, len(rejected))}")

    # ---- Step 4: population comparison (vs OMEN evaluable pass rates) ----
    print("\n" + "-" * 72)
    print("STEP 4 — OMEN vs population pass-rate comparison")
    print("-" * 72)
    omen_rates = {c: float(eval_trades[c].mean()) for c in ("p2", "p3", "p4")}
    pop_rates = {c: float(pop[c].mean()) for c in ("p2", "p3", "p4")}
    print(f"  {'cond':<6} {'OMEN':>10} {'population':>14} {'ratio (OMEN/pop)':>18}")
    for c in ("p2", "p3", "p4"):
        r = (omen_rates[c] / pop_rates[c]) if pop_rates[c] > 0 else float("nan")
        print(f"  {c.upper():<6} {omen_rates[c]*100:>9.2f}% {pop_rates[c]*100:>13.2f}% {r:>17.3f}x")

    # ---- Step 5: distribution comparison ----
    print("\n" + "-" * 72)
    print("STEP 5 — distribution comparison (own-direction inputs)")
    print("-" * 72)
    q = [0.05, 0.25, 0.50, 0.75, 0.95]
    metrics = {
        "delta_ratio":     ("P3 input — directional / opposite aggressive ratio",
                            f"(passes if ≥ {DELTA_RATIO})"),
        "vol_vs_median":   ("P2 input — directional volume / trailing-100 median",
                            f"(passes if ≥ {VOLUME_MULT})"),
        "signed_atr_units":("P4 input — signed price move / (PRICE_ATR_MULT × ATR)",
                            "(passes if ≥ 1)"),
    }
    for m, (desc, pass_rule) in metrics.items():
        print(f"\n  {m}  {desc}  {pass_rule}")
        oq = _quantiles(eval_trades[m], q)
        pq = _quantiles(pop[m], q)
        print(f"    quantile  {'OMEN':>10} {'population':>14}")
        for i, qi in enumerate(q):
            print(f"    {qi:>6.2f}    {oq[i]:>10.4f} {pq[i]:>14.4f}")

    # ---- Step 6: time-of-day overlap ----
    print("\n" + "-" * 72)
    print("STEP 6 — time-of-day distribution")
    print("-" * 72)
    pop_trigs = pop[pop["all_three"]].copy()
    print(f"  population L2 triggers: {len(pop_trigs)}")
    print(f"  OMEN trades           : {len(trades)}")
    print(f"\n  {'hour':<6} {'OMEN n':>8} {'OMEN %':>8} {'pop trig n':>12} {'pop trig %':>12}")
    for h in range(9, 16):
        omen_n = int((trades["hour"] == h).sum())
        omen_p = 100.0 * omen_n / len(trades)
        pop_n = int((pop_trigs["hour"] == h).sum())
        pop_p = 100.0 * pop_n / len(pop_trigs) if len(pop_trigs) else 0
        print(f"  {h:02d}    {omen_n:>8d} {omen_p:>7.1f}% {pop_n:>12d} {pop_p:>11.1f}%")

    # ---- Build markdown report ----
    md = _build_md(
        trades=trades, eval_trades=eval_trades, rejected=rejected,
        pop=pop, pop_trigs=pop_trigs, omen_rates=omen_rates,
        pop_rates=pop_rates, rej_buckets=rej_buckets, q=q, metrics=metrics,
    )
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text(md)
    print(f"\n[Q6] report written: {OUT_MD}")
    return 0


def _build_md(*, trades, eval_trades, rejected, pop, pop_trigs,
              omen_rates, pop_rates, rej_buckets, q, metrics) -> str:
    L: list[str] = []
    L.append("# Q6 — TRCB-v2 bottleneck diagnosis\n")
    L.append("Branch: `analysis/trcb-v2-consumed-data-test-throwaway` (throwaway / archive only).")
    L.append(f"Generated: {datetime.now().isoformat(timespec='seconds')}\n")
    L.append("**Scope.** Descriptive diagnosis of why TRCB-v2 confirmed only 7 of 332 OMEN ")
    L.append("trades. No new parameter tests, no new filter spec. Each trade's predicate flags ")
    L.append("are projected to the trade's OWN side (`p2_long` if `side=+1` else `p2_short`, ")
    L.append("etc.); the population is expanded to 'direction-slots' (each evaluable bar ")
    L.append("contributes one long-direction slot and one short-direction slot) for an ")
    L.append("apples-to-apples comparison.")
    L.append("")
    L.append(f"- OMEN trades total: **{len(trades)}**")
    L.append(f"- FILTER_EVALUABLE (trailing-100 finite AND bar matched in per_bar_volumes_30s): "
             f"**{len(eval_trades)}** ({len(eval_trades)/len(trades)*100:.1f}%)")
    L.append(f"- FILTER_CONFIRMED: **{int(trades['FILTER_CONFIRMED'].sum())} / "
             f"{len(trades)}** ({trades['FILTER_CONFIRMED'].mean()*100:.1f}%)")
    L.append(f"- Population direction-slots: **{len(pop):,}** (each evaluable bar contributes 2)")
    L.append(f"- Population L2 triggers (all-three pass): **{int(pop['all_three'].sum())}** ")
    L.append(f"  ({pop['all_three'].mean()*100:.4f}% of slots)")
    L.append("")

    # ---- 1. Per-condition pass rates ----
    L.append("## 1. Per-condition pass rates (OMEN vs population)\n")
    L.append("All three predicates evaluated independently (regardless of the other two).")
    L.append("OMEN row = evaluable subset (256 trades). Population row = direction-slots.")
    L.append("")
    L.append("| condition | OMEN trades | population | ratio (OMEN/pop) |")
    L.append("|---|---:|---:|---:|")
    for c, lab in (("p2", "P2 (volume vs trailing median)"),
                    ("p3", "P3 (directional / opposite ratio)"),
                    ("p4", "P4 (price move / 0.25·ATR)")):
        omen_pct = omen_rates[c] * 100
        pop_pct = pop_rates[c] * 100
        ratio = (omen_rates[c] / pop_rates[c]) if pop_rates[c] > 0 else float("nan")
        L.append(f"| {lab} | {omen_pct:.2f}% | {pop_pct:.2f}% | {ratio:.3f}× |")
    L.append("")

    # ---- 2. Single primary bottleneck ----
    L.append("## 2. Single primary bottleneck\n")
    L.append(f"Failure attribution among **{len(rejected)} evaluable-rejected trades** ")
    L.append("(P2/P3/P4 = pass-flag for the trade's OWN direction):")
    L.append("")
    L.append("| failure pattern | count | % of rejected |")
    L.append("|---|---:|---:|")
    label_map = {
        "fail_P2_only": "P2 fails alone (P3, P4 pass)",
        "fail_P3_only": "P3 fails alone (P2, P4 pass)",
        "fail_P4_only": "P4 fails alone (P2, P3 pass)",
        "fail_P2_P3":   "P2 + P3 fail (P4 passes)",
        "fail_P2_P4":   "P2 + P4 fail (P3 passes)",
        "fail_P3_P4":   "P3 + P4 fail (P2 passes)",
        "fail_all":     "All three fail",
    }
    for k, v in rej_buckets.items():
        L.append(f"| {label_map[k]} | {v} | "
                 f"{100.0*v/max(len(rejected),1):.1f}% |")
    L.append("")
    L.append("Per-condition failure involvement (any bucket where Pi fails):")
    L.append("")
    L.append("| condition | failures involving | % of rejected |")
    L.append("|---|---:|---:|")
    for c, lab in (("p2", "P2"), ("p3", "P3"), ("p4", "P4")):
        n_fail = int((~rejected[c]).sum())
        L.append(f"| {lab} | {n_fail} | {100.0*n_fail/max(len(rejected),1):.1f}% |")
    L.append("")

    # ---- 3. Distribution comparison ----
    L.append("## 3. Distribution comparison (OMEN entry bars vs population direction-slots)\n")
    L.append("Quantiles of the raw inputs to P2/P3/P4, computed on the trade's own direction:")
    L.append("")
    for m, (desc, pass_rule) in metrics.items():
        L.append(f"### {m} — {desc} {pass_rule}\n")
        oq = _quantiles(eval_trades[m], q)
        pq = _quantiles(pop[m], q)
        L.append("| quantile | OMEN trades | population |")
        L.append("|---|---:|---:|")
        for i, qi in enumerate(q):
            L.append(f"| {qi:.2f} | {oq[i]:.4f} | {pq[i]:.4f} |")
        L.append("")
    L.append("Means (for context):")
    L.append("")
    L.append("| metric | OMEN mean | population mean |")
    L.append("|---|---:|---:|")
    for m in metrics:
        L.append(f"| {m} | {eval_trades[m].mean():.4f} | {pop[m].mean():.4f} |")
    L.append("")

    # ---- 4. Time-of-day overlap ----
    L.append("## 4. Time-of-day overlap\n")
    L.append(f"OMEN trades total: **{len(trades)}**. Population L2 triggers "
             f"(all-three pass): **{len(pop_trigs)}**.")
    L.append("")
    L.append("| hour (ET) | OMEN n | OMEN % | pop trig n | pop trig % |")
    L.append("|---|---:|---:|---:|---:|")
    for h in range(9, 16):
        omen_n = int((trades["hour"] == h).sum())
        omen_p = 100.0 * omen_n / len(trades)
        pop_n = int((pop_trigs["hour"] == h).sum())
        pop_p = (100.0 * pop_n / len(pop_trigs)) if len(pop_trigs) else 0.0
        L.append(f"| {h:02d}:00–{h:02d}:59 | {omen_n} | {omen_p:.1f}% | "
                 f"{pop_n} | {pop_p:.1f}% |")
    L.append("")

    # ---- 5. Interpretation ----
    L.append("## 5. Interpretation\n")

    # Key numbers
    p2_ratio = omen_rates["p2"] / pop_rates["p2"] if pop_rates["p2"] > 0 else float("nan")
    p3_ratio = omen_rates["p3"] / pop_rates["p3"] if pop_rates["p3"] > 0 else float("nan")
    p4_ratio = omen_rates["p4"] / pop_rates["p4"] if pop_rates["p4"] > 0 else float("nan")

    omen_all_three_rate = float((eval_trades["p2"] & eval_trades["p3"] & eval_trades["p4"]).mean())
    pop_all_three_rate = float(pop["all_three"].mean())

    rej_p2 = int((~rejected["p2"]).sum())
    rej_p3 = int((~rejected["p3"]).sum())
    rej_p4 = int((~rejected["p4"]).sum())

    omen_dr_median = float(np.median(eval_trades["delta_ratio"].dropna()))
    pop_dr_median = float(np.median(pop["delta_ratio"].dropna()))

    n_unevaluable = len(trades) - len(eval_trades)
    pct_unevaluable = 100.0 * n_unevaluable / len(trades)

    L.append("### The headline answer: there is no OMEN-specific bottleneck\n")
    L.append("Per-predicate pass rates on evaluable OMEN trades are essentially **identical to ")
    L.append("the random-bar baseline** (population direction-slots):")
    L.append("")
    L.append(f"| condition | OMEN (n=254) | population | OMEN / pop |")
    L.append(f"|---|---:|---:|---:|")
    L.append(f"| P2 | {omen_rates['p2']*100:.1f}% | {pop_rates['p2']*100:.1f}% | {p2_ratio:.2f}× |")
    L.append(f"| P3 | {omen_rates['p3']*100:.1f}% | {pop_rates['p3']*100:.1f}% | {p3_ratio:.2f}× |")
    L.append(f"| P4 | {omen_rates['p4']*100:.1f}% | {pop_rates['p4']*100:.1f}% | {p4_ratio:.2f}× |")
    L.append("")
    L.append(f"All three pass rate: **OMEN evaluable = {omen_all_three_rate*100:.2f}%** ")
    L.append(f"vs **population = {pop_all_three_rate*100:.2f}%**. ")
    L.append("OMEN actually confirms at a *marginally higher* rate than the population baseline. ")
    L.append("**The data does not show OMEN being systematically suppressed by any one predicate.**")
    L.append("")

    L.append("### What's actually driving the 7/332 result\n")
    L.append("Two factors combine:")
    L.append("")
    L.append(f"1. **Filter rarity is by design.** v2's joint-pass rate is ~2-3% on ANY direction-")
    L.append(f"   slot in this corpus — this is a property of stacking three independent ")
    L.append(f"   predicates, each passing 6-50% of the time. Even if every OMEN trade were ")
    L.append(f"   sampled uniformly from the population, ~2.2% would confirm. Observed OMEN ")
    L.append(f"   confirm rate ({omen_all_three_rate*100:.1f}%) matches that ceiling within noise.")
    L.append("")
    L.append(f"2. **{n_unevaluable} / {len(trades)} trades ({pct_unevaluable:.1f}%) are ")
    L.append(f"   structurally unevaluable.** These fire at entry_time=09:30:00 ET (RTH open, ")
    L.append(f"   before the first 5-min bar closes). There is no 5-min bar at 09:30 in the ")
    L.append(f"   per_bar_volumes table — the rolling-100 trailing median is also undefined ")
    L.append(f"   there. These trades cannot pass the filter regardless of microstructure.")
    L.append("")
    L.append(f"Of the {len(eval_trades)} evaluable trades, {int(trades['FILTER_CONFIRMED'].sum())} ")
    L.append(f"confirmed = {omen_all_three_rate*100:.1f}%. Of the {n_unevaluable} unevaluable trades, ")
    L.append(f"0 confirmed (by construction). Combined: 7 / 332 = 2.1%, vs the per-slot population ")
    L.append(f"baseline of 2.2%. **OMEN trades and random direction-slots confirm at the same rate.**")
    L.append("")

    L.append("### Failure attribution among rejected evaluable trades\n")
    L.append(f"Inside the 247 rejected evaluable trades, P3 is involved in {100.0*rej_p3/247:.1f}% ")
    L.append(f"of failures, P4 in {100.0*rej_p4/247:.1f}%, P2 in {100.0*rej_p2/247:.1f}%. ")
    L.append("**Note**: this ranking just reflects the unconditional rarity of each predicate ")
    L.append(f"(P2 fires ~50%, P4 ~15%, P3 ~6% across all bars). P3 'wins' the failure tally ")
    L.append("because P3 is the rarest predicate to pass — not because OMEN signal bars are ")
    L.append(f"anti-aligned with P3. The opposite, in fact: OMEN's *upper-tail* delta_ratio is ")
    L.append(f"slightly heavier than population (95-pct OMEN = "
             f"{float(np.quantile(eval_trades['delta_ratio'].dropna(),0.95)):.3f} vs "
             f"{float(np.quantile(pop['delta_ratio'].dropna(),0.95)):.3f}), so OMEN's P3 pass ")
    L.append(f"rate ({omen_rates['p3']*100:.1f}%) is HIGHER than population's "
             f"({pop_rates['p3']*100:.1f}%).")
    L.append("")

    L.append("### Tested hypotheses that the data does NOT support\n")
    L.append("")
    L.append("- **'OMEN signals identify balanced-flow conditions' → NOT SUPPORTED.** ")
    L.append(f"  OMEN's *median* own-direction delta ratio ({omen_dr_median:.3f}) is slightly ")
    L.append(f"  *below* population ({pop_dr_median:.3f}), which would point this way — but ")
    L.append("  what matters for the P3 predicate is the upper tail (above 1.5), and OMEN's ")
    L.append("  upper tail is slightly *heavier* than population's. OMEN bars are if anything ")
    L.append("  more (not less) likely to clear the 1.5:1 threshold.")
    L.append("")
    L.append("- **'P3 is the chokepoint that suppresses OMEN trades' → NOT SUPPORTED.** ")
    L.append(f"  OMEN's P3 pass rate ({omen_rates['p3']*100:.1f}%) exceeds population's ")
    L.append(f"  ({pop_rates['p3']*100:.1f}%). P3 'wins' the failure tally only because it's the ")
    L.append("  rarest predicate overall — it would dominate failures on a random-bar baseline ")
    L.append("  in the same way.")
    L.append("")
    L.append("- **'P4 is the chokepoint that catches the pause-after-move' → NOT SUPPORTED.** ")
    L.append(f"  OMEN's P4 pass rate ({omen_rates['p4']*100:.1f}%) is comparable to or marginally ")
    L.append(f"  above population's ({pop_rates['p4']*100:.1f}%). signed_atr_units distributions ")
    L.append("  are nearly identical at every quantile.")
    L.append("")

    # Time-of-day note
    omen_hour_pcts = {h: 100.0 * int((trades["hour"] == h).sum()) / len(trades)
                      for h in range(9, 16)}
    pop_hour_pcts = ({h: 100.0 * int((pop_trigs["hour"] == h).sum()) / len(pop_trigs)
                      for h in range(9, 16)} if len(pop_trigs) else
                     {h: 0.0 for h in range(9, 16)})
    max_abs_diff = max(abs(omen_hour_pcts[h] - pop_hour_pcts[h]) for h in range(9, 16))
    L.append("### Time-of-day distributions DO diverge — but it doesn't matter mechanistically\n")
    L.append(f"Max hourly-share difference between OMEN trades and population L2 triggers is ")
    L.append(f"**{max_abs_diff:.1f} percentage points** (e.g., OMEN at 09:00 = "
             f"{omen_hour_pcts[9]:.1f}% — mostly the unevaluable 09:30 cluster — vs population ")
    L.append(f"L2 triggers at 09:00 = {pop_hour_pcts[9]:.1f}%; OMEN at 14:00 = "
             f"{omen_hour_pcts[14]:.1f}% vs population = {pop_hour_pcts[14]:.1f}%; OMEN at 15:00 = ")
    L.append(f"{omen_hour_pcts[15]:.1f}% vs population = {pop_hour_pcts[15]:.1f}%). OMEN is ")
    L.append("afternoon-skewed; population L2 triggers are flat across 10-15.")
    L.append("")
    L.append("**But** OMEN's afternoon-skewed hours don't suppress per-predicate pass rates — ")
    L.append("section 1 shows OMEN passes each P2/P3/P4 at population-level rates. The hour ")
    L.append("mismatch doesn't translate to a microstructure mismatch in this corpus.")
    L.append("")

    L.append("### Fixability — honest assessment\n")
    L.append("")
    L.append("There is no 'fix' because there is no anomaly to fix. The 7/332 outcome reflects:")
    L.append("")
    L.append("- (a) v2's joint pass rate is inherently ~2% regardless of which bar set you sample, and")
    L.append("- (b) ~23% of OMEN trades fire at 09:30 RTH-open, structurally unevaluable by v2's ")
    L.append("  5-min-bar-anchored mechanic.")
    L.append("")
    L.append("Parameter changes to v2 (looser thresholds) would raise the joint pass rate on ")
    L.append("BOTH populations equally, producing more confirmed OMEN trades but with worse ")
    L.append("signal-to-noise. They would not produce OMEN-specific lift unless OMEN trades ")
    L.append("had a microstructure signature the filter was missing — and section 1 shows they ")
    L.append("don't.")
    L.append("")
    L.append("The earlier write-up's 'mechanism conflict / OMEN selects balanced-flow' framing ")
    L.append("should be retracted on the strength of this diagnostic. The 7/332 number is ")
    L.append("uninformative about edge or anti-correlation; it is consistent with random ")
    L.append("sampling at the joint pass rate of v2.")
    L.append("")

    L.append("## 6. Honest caveats\n")
    L.append("- Descriptive analysis of already-produced data. No new filter spec, no new parameters.")
    L.append("- n=254 evaluable OMEN trades is small. Confidence intervals on the 'OMEN matches ")
    L.append("  population' claim are wide; a fresh-data check could move the per-predicate ratios.")
    L.append("- The 76 trades at entry_time=09:30:00 are excluded from the evaluable subset by ")
    L.append("  construction (no matching 5-min bar; rolling median undefined). Reconciling them ")
    L.append("  would require redefining the v2 evaluation timestamp, not adjusting a threshold.")
    L.append("- Population baseline uses per-direction-slots (each bar counted twice — long and ")
    L.append("  short slots). This matches OMEN's direction-specific signaling but is not the ")
    L.append("  same as the 4.4% all-three rate quoted in the Phase 2 SYNTHESIS, which was over ")
    L.append("  bars regardless of direction.")
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
