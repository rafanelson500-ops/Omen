"""TRCB-v1 post-mortem Q1 — delta ratio distribution.

Read existing per_bar_volumes.parquet. For each RTH 5-min bar, compute the
dominant-direction 60s aggressive-volume ratio. Report distribution stats,
percentile of the locked 2.0 threshold, and segmented by hour / day-of-week
(VIX skipped — not in scope for this script).

This is descriptive analysis on already-locked data. No filter re-run.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path("/Users/rafanelson/Omen")
PER_BAR_VOLUMES_PATH = REPO / "diagnostics/mbp10-trcb-v1/per_bar_volumes.parquet"
PHASE2_RESULTS_CSV = REPO / "diagnostics/mbp10-trcb-v1/phase2_population_results.csv"
OUT_MD = REPO / "analysis/trcb-postmortem/q1_ratio_distribution.md"

TIMEZONE = "America/New_York"
TRCB_RATIO_THRESHOLD = 2.0
DIVISOR_FLOOR = 1
TRAILING_MEDIAN_BARS = 100  # for evaluable-bar definition consistency


def main() -> None:
    bv = pd.read_parquet(PER_BAR_VOLUMES_PATH)
    if not isinstance(bv["bar_close_utc"].dtype, pd.DatetimeTZDtype):
        bv["bar_close_utc"] = pd.to_datetime(bv["bar_close_utc"], utc=True)
    bv["bar_close_et"] = bv["bar_close_utc"].dt.tz_convert(TIMEZONE)
    bv["session_date"] = pd.to_datetime(bv["session_date"]).dt.date
    bv = bv.sort_values("bar_close_utc").reset_index(drop=True)

    # Ratios in both directions; ratio_dominant = max of both.
    denom_buy = bv["dir_sell_vol_60s"].clip(lower=DIVISOR_FLOOR)
    denom_sell = bv["dir_buy_vol_60s"].clip(lower=DIVISOR_FLOOR)
    bv["ratio_buy_side"] = bv["dir_buy_vol_60s"] / denom_buy
    bv["ratio_sell_side"] = bv["dir_sell_vol_60s"] / denom_sell
    bv["ratio_dominant"] = bv[["ratio_buy_side", "ratio_sell_side"]].max(axis=1)

    # "evaluable" = bars with at least 1 trade in the window. Otherwise both
    # vols are 0 and ratio = 0/1 = 0 which would pollute the bottom tail.
    eval_mask = bv["n_trades_60s"] > 0
    bv_eval = bv.loc[eval_mask].copy()
    n_total = len(bv)
    n_eval = len(bv_eval)
    print(f"Total bars: {n_total:,}    With ≥1 trade in 60s window: {n_eval:,}")

    rd = bv_eval["ratio_dominant"]

    # ---- distribution stats ----
    pcts = [50, 60, 70, 75, 80, 85, 90, 92.5, 95, 97.5, 99, 99.5]
    pct_values = {p: float(np.percentile(rd, p)) for p in pcts}
    mean_rd = float(rd.mean())
    median_rd = float(rd.median())

    print()
    print(f"Mean ratio_dominant:   {mean_rd:.4f}")
    print(f"Median ratio_dominant: {median_rd:.4f}")
    print()
    print("Percentiles:")
    for p in pcts:
        print(f"  {p:>5.1f}th  →  {pct_values[p]:.4f}")

    # Percentile of 2.0 threshold (pre-reg locked value)
    pct_at_2 = float((rd < TRCB_RATIO_THRESHOLD).mean() * 100)
    pct_at_2_inclusive = float((rd <= TRCB_RATIO_THRESHOLD).mean() * 100)
    print()
    print(f"Locked P3 threshold = {TRCB_RATIO_THRESHOLD}")
    print(f"  % of evaluable bars with ratio_dominant < 2.0:  {pct_at_2:.4f}%")
    print(f"  → 2.0 sits at the {pct_at_2:.2f}th percentile of dominant-side ratio")

    # Top-tail thresholds
    top_10 = float(np.percentile(rd, 90))
    top_5 = float(np.percentile(rd, 95))
    top_1 = float(np.percentile(rd, 99))
    print()
    print(f"Ratio thresholds for top tails:")
    print(f"  top 10% requires ratio ≥ {top_10:.4f}")
    print(f"  top  5% requires ratio ≥ {top_5:.4f}")
    print(f"  top  1% requires ratio ≥ {top_1:.4f}")

    # ---- histogram (20 bins 1.0 – 5.0+) ----
    edges = np.linspace(1.0, 5.0, 20)
    edges = np.append(edges, np.inf)
    counts, _ = np.histogram(rd, bins=edges)
    print()
    print("Histogram (ratio_dominant, n={:,}):".format(n_eval))
    max_count = counts.max()
    BAR_WIDTH = 50
    for i in range(len(edges) - 1):
        lo, hi = edges[i], edges[i + 1]
        n = counts[i]
        pct = n / n_eval * 100
        bar_len = int(round(n / max_count * BAR_WIDTH)) if max_count else 0
        if np.isinf(hi):
            label = f"  ≥{lo:.2f}      "
        else:
            label = f"[{lo:.2f}, {hi:.2f})"
        print(f"  {label:<18s}  {n:>6,}  ({pct:>5.2f}%) {'█' * bar_len}")

    # ---- segmented percentiles by hour-of-day (ET) ----
    bv_eval["hour"] = bv_eval["bar_close_et"].dt.hour
    bv_eval["minute"] = bv_eval["bar_close_et"].dt.minute
    bv_eval["dow"] = bv_eval["bar_close_et"].dt.day_name()

    print()
    print("Percentiles of ratio_dominant by hour-of-day (ET):")
    print(f"  {'hour':>4s}  {'n':>5s}  {'50p':>7s}  {'75p':>7s}  {'90p':>7s}  {'95p':>7s}  {'99p':>7s}  {'pct@2.0':>8s}")
    hour_table = []
    for h in sorted(bv_eval["hour"].unique()):
        s = bv_eval.loc[bv_eval["hour"] == h, "ratio_dominant"]
        row = {
            "hour": h, "n": len(s),
            "p50": float(np.percentile(s, 50)),
            "p75": float(np.percentile(s, 75)),
            "p90": float(np.percentile(s, 90)),
            "p95": float(np.percentile(s, 95)),
            "p99": float(np.percentile(s, 99)),
            "pct_at_2": float((s < TRCB_RATIO_THRESHOLD).mean() * 100),
        }
        hour_table.append(row)
        print(f"  {h:>4d}  {len(s):>5d}  {row['p50']:>7.4f}  {row['p75']:>7.4f}  "
              f"{row['p90']:>7.4f}  {row['p95']:>7.4f}  {row['p99']:>7.4f}  "
              f"{row['pct_at_2']:>7.2f}%")

    print()
    print("Percentiles of ratio_dominant by day-of-week:")
    dow_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    print(f"  {'dow':>10s}  {'n':>5s}  {'50p':>7s}  {'75p':>7s}  {'90p':>7s}  {'95p':>7s}  {'99p':>7s}  {'pct@2.0':>8s}")
    dow_table = []
    for d in dow_order:
        s = bv_eval.loc[bv_eval["dow"] == d, "ratio_dominant"]
        if len(s) == 0:
            continue
        row = {
            "dow": d, "n": len(s),
            "p50": float(np.percentile(s, 50)),
            "p75": float(np.percentile(s, 75)),
            "p90": float(np.percentile(s, 90)),
            "p95": float(np.percentile(s, 95)),
            "p99": float(np.percentile(s, 99)),
            "pct_at_2": float((s < TRCB_RATIO_THRESHOLD).mean() * 100),
        }
        dow_table.append(row)
        print(f"  {d:>10s}  {len(s):>5d}  {row['p50']:>7.4f}  {row['p75']:>7.4f}  "
              f"{row['p90']:>7.4f}  {row['p95']:>7.4f}  {row['p99']:>7.4f}  "
              f"{row['pct_at_2']:>7.2f}%")

    # ---- markdown report ----
    md = []
    md.append("# TRCB-v1 Post-Mortem Q1 — Delta ratio distribution\n")
    md.append("**Source:** `diagnostics/mbp10-trcb-v1/per_bar_volumes.parquet` "
              f"({n_total:,} bars, {n_eval:,} with ≥1 trade in 60s window)\n")
    md.append(f"**Locked TRCB-v1 P3 threshold:** ratio ≥ {TRCB_RATIO_THRESHOLD}\n")

    md.append("## Distribution stats\n")
    md.append(f"- Mean `ratio_dominant`: **{mean_rd:.4f}**")
    md.append(f"- Median `ratio_dominant`: **{median_rd:.4f}**\n")

    md.append("### Percentiles\n")
    md.append("| percentile | ratio_dominant |")
    md.append("|---:|---:|")
    for p in pcts:
        md.append(f"| {p:>4.1f}th | {pct_values[p]:.4f} |")
    md.append("")

    md.append("### Where does the locked 2.0 threshold sit?\n")
    md.append(f"- **{pct_at_2:.2f}th percentile** of dominant-side ratio "
              f"(i.e. {100-pct_at_2:.2f}% of evaluable bars clear it).")
    md.append("- This is the **per-bar dominant-side** rate. Long-only and short-only")
    md.append("  rates are roughly half of this (≈0.27% each in Phase 2 results).\n")

    md.append("### Top-tail thresholds (what ratio would isolate each tail)\n")
    md.append("| tail | ratio_dominant threshold |")
    md.append("|---|---:|")
    md.append(f"| top 10% | ≥ {top_10:.4f} |")
    md.append(f"| top  5% | ≥ {top_5:.4f} |")
    md.append(f"| top  1% | ≥ {top_1:.4f} |\n")

    md.append("## Histogram (1.0 → 5.0+, 20 bins)\n")
    md.append("| bin | n | % |")
    md.append("|---|---:|---:|")
    for i in range(len(edges) - 1):
        lo, hi = edges[i], edges[i + 1]
        n = int(counts[i])
        pct = n / n_eval * 100
        if np.isinf(hi):
            label = f"≥{lo:.2f}"
        else:
            label = f"[{lo:.2f}, {hi:.2f})"
        md.append(f"| {label} | {n:,} | {pct:.2f}% |")
    md.append("")

    md.append("## Segmented percentiles\n")
    md.append("### By hour of day (ET)\n")
    md.append("| hour | n | p50 | p75 | p90 | p95 | p99 | % < 2.0 |")
    md.append("|---:|---:|---:|---:|---:|---:|---:|---:|")
    for r in hour_table:
        md.append(f"| {r['hour']:02d} | {r['n']:,} | {r['p50']:.4f} | {r['p75']:.4f} | "
                  f"{r['p90']:.4f} | {r['p95']:.4f} | {r['p99']:.4f} | {r['pct_at_2']:.2f}% |")
    md.append("")

    md.append("### By day of week\n")
    md.append("| dow | n | p50 | p75 | p90 | p95 | p99 | % < 2.0 |")
    md.append("|---|---:|---:|---:|---:|---:|---:|---:|")
    for r in dow_table:
        md.append(f"| {r['dow']} | {r['n']:,} | {r['p50']:.4f} | {r['p75']:.4f} | "
                  f"{r['p90']:.4f} | {r['p95']:.4f} | {r['p99']:.4f} | {r['pct_at_2']:.2f}% |")
    md.append("")

    md.append("### VIX regime — SKIPPED per task instructions\n")

    md.append("## Reading\n")
    if pct_at_2 >= 95:
        md.append(f"- 2.0 sits at the {pct_at_2:.2f}th percentile of `ratio_dominant`. "
                  "The threshold was effectively asking for a top-tail event by construction. "
                  "**Structurally rare** — the rarity is in P3 alone, not in P3 ∩ P2 ∩ P4.\n")
    elif pct_at_2 >= 80:
        md.append(f"- 2.0 sits at the {pct_at_2:.2f}th percentile — reasonable but tight. "
                  "Rarity at the full-filter level is amplified by intersection with P2/P4.\n")
    else:
        md.append(f"- 2.0 sits at the {pct_at_2:.2f}th percentile — not a tight threshold by itself. "
                  "Rarity at the full-filter level comes from intersection with other predicates.\n")

    md.append("## Disclaimer\n")
    md.append("This is descriptive analysis on already-locked data. The TRCB-v1 FAIL verdict "
              "is unaffected. No new filter run is authorized.\n")

    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(md))
    print(f"\nSaved: {OUT_MD}")


if __name__ == "__main__":
    main()
