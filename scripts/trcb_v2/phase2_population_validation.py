"""TRCB-v2 Phase 2 — population validation on the SAME 160-session corpus.

THROWAWAY IN-SAMPLE ANALYSIS. See common.CRITICAL_DISCLOSURE.

Mirrors trcb_filter/phase2_population_validation.py with three changes:
  - WINDOW_SECONDS=30, DELTA_RATIO=1.5 (v2 params)
  - Multi-horizon forward returns: 1m, 5m, 15m, 25m (was 25m only)
  - Side-by-side comparison vs v1 Phase 2 reference in the report

Trigger rule: for each evaluable RTH 5-min bar close T,
  P2 (30s directional volume ≥ trailing-100-bar median × VOLUME_MULT)
  P3 (directional / opposite aggressive ratio ≥ DELTA_RATIO)
  P4 (signed price move in [T, T+30s) ≥ PRICE_ATR_MULT × Wilder ATR(14))
  all three for the same direction → trcb_long / trcb_short
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as sps

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (  # noqa: E402
    ATR_WINDOW, BAR_FREQ, CRITICAL_DISCLOSURE, DELTA_RATIO, DIVISOR_FLOOR,
    ES_1S_PATH, FORWARD_HORIZONS_MIN, OUTPUT_ANALYSIS_DIR, PER_BAR_VOLUMES_PATH,
    PHASE2_REPORT_MD, PHASE2_RESULTS_CSV, PRICE_ATR_MULT, TIMEZONE,
    TRAILING_MEDIAN_BARS, V1_PHASE2_CSV, VOLUME_MULT, WINDOW_SECONDS,
    true_range, wilder_atr,
)


def _stat_block(name: str, s: pd.Series) -> dict:
    if len(s) == 0:
        return {"name": name, "n": 0}
    std = float(s.std(ddof=1)) if len(s) > 1 else float("nan")
    t = (float(s.mean() / (std / np.sqrt(len(s))))
         if len(s) > 1 and std > 0 else float("nan"))
    return {
        "name": name, "n": len(s),
        "mean": float(s.mean()), "median": float(s.median()),
        "std": std,
        "min": float(s.min()), "max": float(s.max()),
        "t_vs_zero": t,
        "pct_positive": float((s > 0).mean()),
    }


def _print_stat(blk: dict) -> str:
    if blk.get("n", 0) == 0:
        return f"  {blk['name']}: n=0"
    return (f"  {blk['name']}: n={blk['n']:,}  "
            f"mean={blk['mean']:+.4f}  median={blk['median']:+.4f}  "
            f"std={blk['std']:.4f}  t={blk['t_vs_zero']:+.4f}  "
            f"%>0={blk['pct_positive']*100:.2f}%")


def main() -> None:
    OUTPUT_ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)
    print(CRITICAL_DISCLOSURE)
    print("=" * 72)
    print("TRCB-v2 PHASE 2 — POPULATION VALIDATION (IN-SAMPLE)")
    print("=" * 72)
    print(f"  WINDOW_SECONDS = {WINDOW_SECONDS}")
    print(f"  VOLUME_MULT    = {VOLUME_MULT}")
    print(f"  DELTA_RATIO    = {DELTA_RATIO}")
    print(f"  PRICE_ATR_MULT = {PRICE_ATR_MULT}")
    print(f"  ATR_WINDOW     = {ATR_WINDOW}")
    print()

    # ---- Per-bar volumes ----
    bv = pd.read_parquet(PER_BAR_VOLUMES_PATH)
    if not isinstance(bv["bar_close_utc"].dtype, pd.DatetimeTZDtype):
        bv["bar_close_utc"] = pd.to_datetime(bv["bar_close_utc"], utc=True)
    bv["bar_close_et"] = bv["bar_close_utc"].dt.tz_convert(TIMEZONE)
    bv["session_date"] = pd.to_datetime(bv["session_date"]).dt.date
    bv = bv.sort_values("bar_close_utc").reset_index(drop=True)
    print(f"per_bar_volumes_30s (raw): {len(bv):,} bars across "
          f"{bv['session_date'].nunique()} sessions")

    # Filter to the 160-session corpus v1 used (for apples-to-apples comparison).
    # The 9-day data refresh (Apr 29 → May 11 2026) is excluded from this in-sample test.
    if V1_PHASE2_CSV.exists():
        v1 = pd.read_csv(V1_PHASE2_CSV, usecols=["session_date"])
        v1_sessions = set(pd.to_datetime(v1["session_date"]).dt.date.unique())
        before = len(bv)
        bv = bv[bv["session_date"].isin(v1_sessions)].copy()
        bv = bv.sort_values("bar_close_utc").reset_index(drop=True)
        print(f"  filtered to v1's session set: {bv['session_date'].nunique()} sessions, "
              f"{len(bv):,} bars (dropped {before - len(bv):,} bars from {len(v1_sessions) - bv['session_date'].nunique() + 0} new days)")
    else:
        print(f"  WARNING: v1 reference not found at {V1_PHASE2_CSV}; using full corpus")

    # ---- Trailing 100-bar median (strictly preceding via shift(1)) ----
    bv["median_buy_100"] = bv["dir_buy_vol_30s"].rolling(
        TRAILING_MEDIAN_BARS, min_periods=TRAILING_MEDIAN_BARS
    ).median().shift(1)
    bv["median_sell_100"] = bv["dir_sell_vol_30s"].rolling(
        TRAILING_MEDIAN_BARS, min_periods=TRAILING_MEDIAN_BARS
    ).median().shift(1)
    n_p2_eval = int(bv["median_buy_100"].notna().sum())
    print(f"P2-evaluable bars (trailing-100 finite): {n_p2_eval:,}")

    # ---- ES 1s → 5-min ATR(14) Wilder ----
    es_1s = pd.read_parquet(ES_1S_PATH, columns=["open", "high", "low", "close"])
    if not isinstance(es_1s.index.dtype, pd.DatetimeTZDtype):
        es_1s.index = pd.to_datetime(es_1s.index, utc=True).tz_convert(TIMEZONE)
    print(f"ES 1s: {len(es_1s):,} rows, {es_1s.index.min()} → {es_1s.index.max()}")

    es_5min = (es_1s.resample(BAR_FREQ, label="right", closed="right")
                    .agg({"open": "first", "high": "max", "low": "min", "close": "last"})
                    .dropna(subset=["close"]))
    es_5min["tr"] = true_range(es_5min["high"], es_5min["low"], es_5min["close"])
    es_5min["atr"] = wilder_atr(es_5min["tr"], ATR_WINDOW)

    bv = bv.set_index("bar_close_et")
    bv["price_at_T"] = es_5min["close"].reindex(bv.index)
    bv["atr_at_T"] = es_5min["atr"].reindex(bv.index)
    bv = bv.reset_index()

    # P4 reference: price at T + 30s
    target_p4 = pd.DatetimeIndex(bv["bar_close_et"] + pd.Timedelta(seconds=WINDOW_SECONDS))
    bv["price_at_T_plus_30s"] = es_1s["close"].reindex(
        target_p4, method="ffill", tolerance=pd.Timedelta("5s")
    ).values
    bv["price_move_30s"] = bv["price_at_T_plus_30s"] - bv["price_at_T"]
    bv["p4_threshold"] = PRICE_ATR_MULT * bv["atr_at_T"]
    bv["p4_long"] = bv["price_move_30s"] >= bv["p4_threshold"]
    bv["p4_short"] = (-bv["price_move_30s"]) >= bv["p4_threshold"]

    # P2 / P3
    bv["p2_long"] = bv["dir_buy_vol_30s"] >= (VOLUME_MULT * bv["median_buy_100"])
    bv["p2_short"] = bv["dir_sell_vol_30s"] >= (VOLUME_MULT * bv["median_sell_100"])
    denom_long = bv["dir_sell_vol_30s"].clip(lower=DIVISOR_FLOOR)
    denom_short = bv["dir_buy_vol_30s"].clip(lower=DIVISOR_FLOOR)
    bv["delta_ratio_long"] = bv["dir_buy_vol_30s"] / denom_long
    bv["delta_ratio_short"] = bv["dir_sell_vol_30s"] / denom_short
    bv["p3_long"] = bv["delta_ratio_long"] >= DELTA_RATIO
    bv["p3_short"] = bv["delta_ratio_short"] >= DELTA_RATIO

    base_eval = (
        bv["median_buy_100"].notna() & bv["median_sell_100"].notna()
        & bv["price_at_T"].notna() & bv["price_at_T_plus_30s"].notna()
        & bv["atr_at_T"].notna()
    )
    bv["trcb_long"] = (bv["p2_long"] & bv["p3_long"] & bv["p4_long"]).fillna(False) & base_eval
    bv["trcb_short"] = (bv["p2_short"] & bv["p3_short"] & bv["p4_short"]).fillna(False) & base_eval

    # ---- Multi-horizon forward returns ----
    for h_min in FORWARD_HORIZONS_MIN:
        target_idx = pd.DatetimeIndex(bv["bar_close_et"] + pd.Timedelta(minutes=h_min))
        px = es_1s["close"].reindex(target_idx, method="ffill",
                                    tolerance=pd.Timedelta("5s")).values
        # Same-session truncation
        target_sess = pd.Series(target_idx.date)
        bv_sess = bv["session_date"].reset_index(drop=True)
        same_session = (target_sess == bv_sess).values
        raw_col = f"fwd_ret_{h_min}min_raw"
        signed_col = f"fwd_ret_{h_min}min_signed"
        bv[raw_col] = np.where(same_session, px - bv["price_at_T"].values, np.nan)
        bv[signed_col] = np.nan
        bv.loc[bv["trcb_long"], signed_col] = bv.loc[bv["trcb_long"], raw_col]
        bv.loc[bv["trcb_short"], signed_col] = -bv.loc[bv["trcb_short"], raw_col]

    # ---- Summary stats ----
    n_evaluable = int(base_eval.sum())
    n_long = int(bv["trcb_long"].sum())
    n_short = int(bv["trcb_short"].sum())
    n_trig = n_long + n_short
    trig_rate = n_trig / n_evaluable if n_evaluable else 0.0

    print()
    print("=" * 72)
    print("TRIGGER COUNTS")
    print("=" * 72)
    print(f"  Total RTH bars                 : {len(bv):,}")
    print(f"  Fully evaluable                : {n_evaluable:,}")
    print(f"  Triggered LONG                 : {n_long:,}")
    print(f"  Triggered SHORT                : {n_short:,}")
    print(f"  Total triggered                : {n_trig:,}")
    print(f"  Trigger rate (of evaluable)    : {trig_rate*100:.4f}%")

    print("\nPer-predicate pass counts (on evaluable bars, per direction):")
    for d in ("long", "short"):
        p2 = int((bv[f"p2_{d}"] & base_eval).sum())
        p3 = int((bv[f"p3_{d}"] & base_eval).sum())
        p4 = int((bv[f"p4_{d}"] & base_eval).sum())
        p_all = int(bv[f"trcb_{d}"].sum())
        print(f"  {d:5s}: P2={p2:,}  P3={p3:,}  P4={p4:,}  all-three={p_all:,}")

    # Forward-return stats at each horizon
    trig_mask = bv["trcb_long"] | bv["trcb_short"]
    print("\n" + "=" * 72)
    print("MULTI-HORIZON FORWARD-RETURN STATS")
    print("=" * 72)
    horizon_blocks: dict[int, dict] = {}
    for h in FORWARD_HORIZONS_MIN:
        signed_col = f"fwd_ret_{h}min_signed"
        raw_col = f"fwd_ret_{h}min_raw"
        s_trig = _stat_block(f"triggered (signed, {h}m)",
                             bv.loc[trig_mask, signed_col].dropna())
        s_all_raw = _stat_block(f"all-eval (raw, {h}m)",
                                bv.loc[base_eval, raw_col].dropna())
        # per-direction
        s_long = _stat_block(f"triggered LONG (signed, {h}m)",
                             bv.loc[bv["trcb_long"], signed_col].dropna())
        s_short = _stat_block(f"triggered SHORT (signed, {h}m)",
                              bv.loc[bv["trcb_short"], signed_col].dropna())
        welch_t = welch_p = float("nan")
        s_trig_data = bv.loc[trig_mask, signed_col].dropna()
        s_all_data = bv.loc[base_eval, raw_col].dropna()
        if len(s_trig_data) >= 3 and len(s_all_data) >= 3:
            w = sps.ttest_ind(s_trig_data, s_all_data,
                              equal_var=False, nan_policy="omit")
            welch_t = float(w.statistic); welch_p = float(w.pvalue)
        horizon_blocks[h] = {
            "trig": s_trig, "all_raw": s_all_raw,
            "long": s_long, "short": s_short,
            "welch_t": welch_t, "welch_p": welch_p,
        }
        print(f"\n--- horizon = {h} min ---")
        print(_print_stat(s_trig))
        print(_print_stat(s_all_raw))
        print(_print_stat(s_long))
        print(_print_stat(s_short))
        print(f"  Welch trig (signed) vs all-eval (raw): "
              f"t={welch_t:+.4f}  p={welch_p:.6f}")

    # Hour-of-day
    bv["hour_only"] = bv["bar_close_et"].dt.hour
    print("\n" + "=" * 72)
    print("TRIGGER RATE BY HOUR (ET, evaluable bars)")
    print("=" * 72)
    for h_start in range(9, 16):
        mask = base_eval & (bv["hour_only"] == h_start)
        n_b = int(mask.sum()); n_t = int((mask & trig_mask).sum())
        rate = n_t / n_b if n_b else 0.0
        print(f"  {h_start:02d}:00–{h_start:02d}:59  evaluable={n_b:>5d}  "
              f"triggers={n_t:>4d}  rate={rate*100:>6.3f}%")

    # ---- Comparison vs v1 ----
    print("\n" + "=" * 72)
    print("COMPARISON vs TRCB-v1 Phase 2 (reference, in-sample on same corpus)")
    print("=" * 72)
    v1_compare = _v1_summary()
    print(v1_compare)

    # ---- Persist + report ----
    bv.to_csv(PHASE2_RESULTS_CSV, index=False)
    print(f"\nSaved: {PHASE2_RESULTS_CSV}")

    md = _build_report(
        bv=bv, base_eval=base_eval, trig_mask=trig_mask,
        n_long=n_long, n_short=n_short, n_evaluable=n_evaluable,
        trig_rate=trig_rate, horizon_blocks=horizon_blocks,
        v1_compare=v1_compare,
    )
    PHASE2_REPORT_MD.write_text(md)
    print(f"Saved: {PHASE2_REPORT_MD}")


def _v1_summary() -> str:
    """Load v1 Phase 2 results and return a short text comparison."""
    if not V1_PHASE2_CSV.exists():
        return "  v1 Phase 2 CSV not found — skipping comparison.\n"
    v1 = pd.read_csv(V1_PHASE2_CSV)
    n_long = int(v1["trcb_long"].sum())
    n_short = int(v1["trcb_short"].sum())
    trig = v1[v1["trcb_long"] | v1["trcb_short"]].copy()
    n_trig = len(trig)
    if "fwd_ret_25min_signed" in v1.columns:
        signed = trig["fwd_ret_25min_signed"].dropna()
    else:
        signed = pd.Series([], dtype=float)
    if len(signed) > 1:
        mean = signed.mean(); std = signed.std(ddof=1)
        t = mean / (std / np.sqrt(len(signed))) if std > 0 else float("nan")
        pos = float((signed > 0).mean()) * 100
    else:
        mean = std = t = pos = float("nan")
    return (f"  v1 (60s window, 2.0:1 ratio): n_trig={n_trig}  "
            f"(long={n_long}, short={n_short})\n"
            f"  v1 triggered signed 25m return: mean={mean:+.4f}  "
            f"t={t:+.4f}  %>0={pos:.2f}%")


def _build_report(**kw) -> str:
    bv = kw["bv"]; base_eval = kw["base_eval"]; trig_mask = kw["trig_mask"]
    horizon_blocks = kw["horizon_blocks"]
    parts: list[str] = []
    parts.append("# TRCB-v2 Phase 2 — Population Validation (IN-SAMPLE, THROWAWAY)\n")
    parts.append(CRITICAL_DISCLOSURE)
    parts.append("")
    parts.append(f"**Generated:** {datetime.now().isoformat(timespec='seconds')}")
    parts.append(f"**Branch:** `analysis/trcb-v2-consumed-data-test-throwaway`\n")
    parts.append("## Locked parameters (v2)\n")
    parts.append(f"- WINDOW_SECONDS = {WINDOW_SECONDS}")
    parts.append(f"- VOLUME_MULT    = {VOLUME_MULT}")
    parts.append(f"- DELTA_RATIO    = {DELTA_RATIO}")
    parts.append(f"- PRICE_ATR_MULT = {PRICE_ATR_MULT}")
    parts.append(f"- ATR_WINDOW     = {ATR_WINDOW} (Wilder RMA on 5-min bars)\n")

    parts.append("## Corpus")
    parts.append(f"- Total RTH 5-min bars: **{len(bv):,}**")
    parts.append(f"- Fully evaluable bars: **{kw['n_evaluable']:,}**")
    parts.append(f"- Sessions: **{bv['session_date'].nunique()}**")
    parts.append(f"- Date range: {bv['session_date'].min()} → {bv['session_date'].max()}\n")

    parts.append("## Trigger counts")
    parts.append(f"- Triggered LONG: **{kw['n_long']:,}**")
    parts.append(f"- Triggered SHORT: **{kw['n_short']:,}**")
    parts.append(f"- Total: **{kw['n_long']+kw['n_short']:,}**")
    parts.append(f"- Trigger rate of evaluable: **{kw['trig_rate']*100:.4f}%**\n")

    parts.append("## Per-predicate pass counts (evaluable bars)")
    parts.append("| direction | P2 | P3 | P4 | all-three |")
    parts.append("|---|---:|---:|---:|---:|")
    for d in ("long", "short"):
        p2 = int((bv[f"p2_{d}"] & base_eval).sum())
        p3 = int((bv[f"p3_{d}"] & base_eval).sum())
        p4 = int((bv[f"p4_{d}"] & base_eval).sum())
        p_all = int(bv[f"trcb_{d}"].sum())
        parts.append(f"| {d} | {p2:,} | {p3:,} | {p4:,} | {p_all:,} |")
    parts.append("")

    parts.append("## Forward-return signal by horizon")
    parts.append("| horizon | n (triggered) | mean signed | std | t vs 0 | %>0 | Welch t vs all-eval-raw | Welch p |")
    parts.append("|---|---:|---:|---:|---:|---:|---:|---:|")
    for h in FORWARD_HORIZONS_MIN:
        blk = horizon_blocks[h]; s = blk["trig"]
        if s.get("n", 0) == 0:
            parts.append(f"| {h} min | 0 | — | — | — | — | — | — |"); continue
        parts.append(
            f"| {h} min | {s['n']:,} | {s['mean']:+.4f} | {s['std']:.4f} | "
            f"{s['t_vs_zero']:+.4f} | {s['pct_positive']*100:.2f}% | "
            f"{blk['welch_t']:+.4f} | {blk['welch_p']:.6f} |"
        )
    parts.append("")

    parts.append("## Per-direction signal (signed return at each horizon)")
    parts.append("| horizon | long n | long mean | long t | short n | short mean | short t |")
    parts.append("|---|---:|---:|---:|---:|---:|---:|")
    for h in FORWARD_HORIZONS_MIN:
        blk = horizon_blocks[h]
        sl = blk["long"]; ss = blk["short"]
        sl_n = sl.get("n", 0); ss_n = ss.get("n", 0)
        sl_mean = f"{sl.get('mean', float('nan')):+.4f}" if sl_n else "—"
        sl_t = f"{sl.get('t_vs_zero', float('nan')):+.4f}" if sl_n > 1 else "—"
        ss_mean = f"{ss.get('mean', float('nan')):+.4f}" if ss_n else "—"
        ss_t = f"{ss.get('t_vs_zero', float('nan')):+.4f}" if ss_n > 1 else "—"
        parts.append(f"| {h} min | {sl_n} | {sl_mean} | {sl_t} | "
                     f"{ss_n} | {ss_mean} | {ss_t} |")
    parts.append("")

    parts.append("## Trigger rate by hour (ET, evaluable bars)")
    parts.append("| hour | evaluable | triggers | rate |")
    parts.append("|---|---:|---:|---:|")
    for h_start in range(9, 16):
        mask = base_eval & (bv["hour_only"] == h_start)
        n_b = int(mask.sum()); n_t = int((mask & trig_mask).sum())
        rate = n_t / n_b if n_b else 0.0
        parts.append(f"| {h_start:02d}:00–{h_start:02d}:59 | {n_b:,} | "
                     f"{n_t:,} | {rate*100:.3f}% |")
    parts.append("")

    parts.append("## Reference: TRCB-v1 Phase 2 (same corpus, different parameters)\n")
    parts.append("```")
    parts.append(kw["v1_compare"])
    parts.append("```\n")

    parts.append("## In-sample-status reminder\n")
    parts.append("These numbers describe how the 30s/1.5:1 parameter set behaves on the ")
    parts.append("160-session corpus that the post-mortem already informed. They do not ")
    parts.append("constitute validation. See the CRITICAL DISCLOSURE at the top of this file.")
    return "\n".join(parts) + "\n"


if __name__ == "__main__":
    main()
