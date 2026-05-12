"""TRCB-v1 post-mortem Q3 — forward-return horizon sensitivity.

For the existing 27 TRCB-v1 triggered bars from Phase 2, compute signed
forward returns at 1 / 5 / 15 / 25 / 60 minute horizons. Compare against the
unconditional population baseline (raw, no direction) at each horizon.

No new filter run. Pure horizon-sweep on locked-60s triggered set.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path("/Users/rafanelson/Omen")
PHASE2_RESULTS_CSV = REPO / "diagnostics/mbp10-trcb-v1/phase2_population_results.csv"
ES_1S_PATH = REPO / "backend/data/market/ES_c_0_ohlcv1s_2025-09-08_2026-04-27.parquet"
OUT_MD = REPO / "analysis/trcb-postmortem/q3_forward_horizons.md"

TIMEZONE = "America/New_York"
HORIZONS_MIN = [1, 5, 15, 25, 60]


def main() -> None:
    print("Loading Phase 2 results + ES 1s closes…")
    p2 = pd.read_csv(PHASE2_RESULTS_CSV)
    # Parse timestamps; bar_close_et is what we'll key on for ET lookups
    p2["bar_close_et"] = pd.to_datetime(p2["bar_close_et"], utc=True).dt.tz_convert(TIMEZONE)
    p2["session_date"] = pd.to_datetime(p2["session_date"]).dt.date
    # Booleans coming from CSV are strings; coerce
    for c in ("trcb_long", "trcb_short", "p2_long", "p2_short", "p3_long", "p3_short",
              "p4_long", "p4_short"):
        if c in p2.columns:
            p2[c] = p2[c].map({"True": True, "False": False, True: True, False: False,
                               "TRUE": True, "FALSE": False, 1: True, 0: False}).fillna(False)

    triggered_mask = p2["trcb_long"] | p2["trcb_short"]
    triggered = p2.loc[triggered_mask].copy().reset_index(drop=True)
    print(f"  Phase 2 rows: {len(p2):,}")
    print(f"  triggered rows: {len(triggered)} "
          f"(long={int(p2['trcb_long'].sum())}, short={int(p2['trcb_short'].sum())})")
    assert len(triggered) == 27, f"Expected 27 triggered bars, got {len(triggered)}"

    es_1s = pd.read_parquet(ES_1S_PATH, columns=["close"])
    if not isinstance(es_1s.index.dtype, pd.DatetimeTZDtype):
        es_1s.index = pd.to_datetime(es_1s.index, utc=True).tz_convert(TIMEZONE)
    es_close = es_1s["close"]

    # Build evaluable-bar mask = bars where Phase 2 deemed "base_eval" passed.
    # Phase 2 didn't write base_eval explicitly. Recover it: median_buy/sell finite
    # AND price_at_T finite AND price_at_T_plus_60 finite AND atr_at_T finite.
    eval_mask = (
        p2["median_buy_100"].notna() & p2["median_sell_100"].notna()
        & p2["price_at_T"].notna() & p2["price_at_T_plus_60"].notna()
        & p2["atr_at_T"].notna()
    )
    print(f"  evaluable bars (Phase 2 base_eval): {int(eval_mask.sum()):,}")

    # ---- Compute forward returns at each horizon for triggered + population ----
    print("\nComputing forward returns at each horizon…")
    horizon_results = []
    # Pre-compute per-bar prices for triggered subset (small set)
    for h in HORIZONS_MIN:
        # Triggered subset signed returns
        trig_signed = []
        trig_long_signed = []
        trig_short_signed = []
        for _, row in triggered.iterrows():
            t_et = row["bar_close_et"]
            target_et = t_et + pd.Timedelta(minutes=h)
            # Must stay in same session
            if target_et.date() != row["session_date"]:
                continue
            try:
                p_t = es_close.asof(t_et)
                p_tp = es_close.asof(target_et)
            except Exception:
                continue
            if pd.isna(p_t) or pd.isna(p_tp):
                continue
            raw_move = float(p_tp) - float(p_t)
            if row["trcb_long"]:
                signed = raw_move
                trig_long_signed.append(signed)
            elif row["trcb_short"]:
                signed = -raw_move
                trig_short_signed.append(signed)
            else:
                continue
            trig_signed.append(signed)

        trig_signed = np.array(trig_signed, dtype=float)
        trig_long_signed = np.array(trig_long_signed, dtype=float)
        trig_short_signed = np.array(trig_short_signed, dtype=float)

        # Unconditional population at horizon h: raw (no direction) on evaluable bars
        # For efficiency, compute via vectorized DatetimeIndex reindex on the full p2 frame
        p2_eval = p2.loc[eval_mask].copy()
        target_idx = pd.DatetimeIndex(
            p2_eval["bar_close_et"] + pd.Timedelta(minutes=h)
        )
        target_session = pd.Series(target_idx.date, index=p2_eval.index)
        same_sess = target_session == p2_eval["session_date"]
        p_t = es_close.reindex(
            pd.DatetimeIndex(p2_eval["bar_close_et"]),
            method="ffill", tolerance=pd.Timedelta("5s"),
        )
        p_tp = es_close.reindex(
            target_idx, method="ffill", tolerance=pd.Timedelta("5s"),
        )
        raw = p_tp.values - p_t.values
        raw = np.where(same_sess.values, raw, np.nan)
        uncond = pd.Series(raw).dropna().values

        def stat(name, arr):
            n = len(arr)
            if n == 0:
                return {"name": name, "n": 0}
            mean = float(np.mean(arr))
            std = float(np.std(arr, ddof=1)) if n > 1 else float("nan")
            t = float(mean / (std / np.sqrt(n))) if n > 1 and std > 0 else float("nan")
            return {
                "name": name, "n": n,
                "mean": mean, "median": float(np.median(arr)),
                "std": std, "t_vs_zero": t,
                "pct_pos": float(np.mean(arr > 0) * 100),
            }

        s_trig = stat("triggered (signed, both dirs)", trig_signed)
        s_long = stat("triggered LONG (signed)", trig_long_signed)
        s_short = stat("triggered SHORT (signed)", trig_short_signed)
        s_uncond = stat("unconditional (raw)", uncond)
        sep = (s_trig["mean"] - s_uncond["mean"]) if s_trig.get("n") and s_uncond.get("n") else float("nan")

        horizon_results.append({
            "horizon_min": h,
            "n_trig": s_trig.get("n", 0),
            "trig_mean": s_trig.get("mean", float("nan")),
            "trig_t": s_trig.get("t_vs_zero", float("nan")),
            "trig_pct_pos": s_trig.get("pct_pos", float("nan")),
            "long_n": s_long.get("n", 0),
            "long_mean": s_long.get("mean", float("nan")),
            "long_pct_pos": s_long.get("pct_pos", float("nan")),
            "short_n": s_short.get("n", 0),
            "short_mean": s_short.get("mean", float("nan")),
            "short_pct_pos": s_short.get("pct_pos", float("nan")),
            "uncond_n": s_uncond.get("n", 0),
            "uncond_mean": s_uncond.get("mean", float("nan")),
            "sep_vs_uncond": sep,
        })
        print(f"  horizon={h:>3d}min  "
              f"n_trig={s_trig.get('n',0):>3d}  "
              f"mean_signed={s_trig.get('mean', float('nan')):+.4f}  "
              f"t={s_trig.get('t_vs_zero', float('nan')):+.4f}  "
              f"sep={sep:+.4f}  "
              f"long({s_long.get('n',0)}):{s_long.get('mean', float('nan')):+.4f}  "
              f"short({s_short.get('n',0)}):{s_short.get('mean', float('nan')):+.4f}")

    # ---- Build comparison table ----
    print()
    print("=" * 96)
    print("FORWARD HORIZON SENSITIVITY (locked-60s triggered set, n=27)")
    print("=" * 96)
    header = (
        f"  {'h_min':>5s}  {'n_tr':>4s}  {'mean_sgn':>9s}  {'t_vs0':>7s}  "
        f"{'%pos':>5s}  {'long_n':>6s}  {'long_mean':>10s}  {'short_n':>7s}  "
        f"{'short_mean':>11s}  {'uncond_mean':>11s}  {'sep_uncond':>11s}"
    )
    print(header)
    for r in horizon_results:
        print(f"  {r['horizon_min']:>5d}  {r['n_trig']:>4d}  "
              f"{r['trig_mean']:>+9.4f}  {r['trig_t']:>+7.4f}  "
              f"{r['trig_pct_pos']:>4.1f}%  {r['long_n']:>6d}  "
              f"{r['long_mean']:>+10.4f}  {r['short_n']:>7d}  "
              f"{r['short_mean']:>+11.4f}  {r['uncond_mean']:>+11.4f}  "
              f"{r['sep_vs_uncond']:>+11.4f}")

    # ---- Markdown ----
    md = []
    md.append("# TRCB-v1 Post-Mortem Q3 — Forward-return horizon sensitivity\n")
    md.append(f"**Source:** locked-60s triggered set from Phase 2 (n=27: 15 long + 12 short)")
    md.append(f"\n**Horizons evaluated:** {HORIZONS_MIN} minutes")
    md.append(f"\n**Unconditional baseline:** raw (no direction) forward return on "
              f"{int(eval_mask.sum()):,} evaluable bars at each horizon.\n")

    md.append("## Combined triggered set (both directions, signed)\n")
    md.append("| horizon (min) | n | mean signed | t vs 0 | % > 0 | uncond mean | sep vs uncond |")
    md.append("|---:|---:|---:|---:|---:|---:|---:|")
    for r in horizon_results:
        md.append(f"| {r['horizon_min']} | {r['n_trig']} | "
                  f"{r['trig_mean']:+.4f} | {r['trig_t']:+.4f} | "
                  f"{r['trig_pct_pos']:.1f}% | {r['uncond_mean']:+.4f} | "
                  f"{r['sep_vs_uncond']:+.4f} |")
    md.append("")

    md.append("## Per-direction breakdown\n")
    md.append("| horizon (min) | long_n | long_mean | long_%pos | short_n | short_mean | short_%pos |")
    md.append("|---:|---:|---:|---:|---:|---:|---:|")
    for r in horizon_results:
        md.append(f"| {r['horizon_min']} | {r['long_n']} | {r['long_mean']:+.4f} | "
                  f"{r['long_pct_pos']:.1f}% | {r['short_n']} | {r['short_mean']:+.4f} | "
                  f"{r['short_pct_pos']:.1f}% |")
    md.append("")

    md.append("## Reading\n")
    # Identify best horizon by signed mean and by t-stat
    valid = [r for r in horizon_results if r["n_trig"] > 0]
    if valid:
        best_by_mean = max(valid, key=lambda r: r["trig_mean"] if not np.isnan(r["trig_mean"]) else -1e9)
        best_by_t = max(valid, key=lambda r: r["trig_t"] if not np.isnan(r["trig_t"]) else -1e9)
        md.append(f"- Best horizon by signed mean: **{best_by_mean['horizon_min']} min** "
                  f"(mean = {best_by_mean['trig_mean']:+.4f}, n = {best_by_mean['n_trig']})")
        md.append(f"- Best horizon by t-statistic: **{best_by_t['horizon_min']} min** "
                  f"(t = {best_by_t['trig_t']:+.4f}, mean = {best_by_t['trig_mean']:+.4f})")
        md.append(f"- 25-min horizon (Phase 2 default): mean = "
                  f"{[r for r in horizon_results if r['horizon_min']==25][0]['trig_mean']:+.4f}, "
                  f"t = {[r for r in horizon_results if r['horizon_min']==25][0]['trig_t']:+.4f}\n")
    else:
        md.append("- No valid horizon results.\n")

    md.append("## Caveats\n")
    md.append("- n=27 is small. t-statistics with this sample size are noisy. **Do not "
              "overclaim**: even an apparently significant t at any horizon is consistent "
              "with random variation given the multiple-horizon look.")
    md.append("- Short-side n=12 and long-side n=15 are even smaller subsets — per-direction "
              "means are highly volatile.")
    md.append("- Forward return at 60min frequently rolls outside RTH; same-session check "
              "drops bars whose horizon would land past 16:00 ET.\n")

    md.append("## Disclaimer\n")
    md.append("Diagnostic only. TRCB-v1 FAIL verdict unaffected. No new filter authorized.\n")

    OUT_MD.write_text("\n".join(md))
    print(f"\nSaved: {OUT_MD}")


if __name__ == "__main__":
    main()
