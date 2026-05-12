"""Phase 2 — Population-level validation of the TRCB filter.

For every RTH 5-min bar close T in the corpus, evaluate the three predicates
P2/P3/P4 per pre-reg Section 4. For bars that trigger, compute the signed
25-min forward return (signed by the implied direction). Report population
stats and a qualitative verdict.

Outputs:
  diagnostics/mbp10-trcb-v1/phase2_population_results.csv
  diagnostics/mbp10-trcb-v1/phase2_summary_report.md

Read per-bar 60s volumes from PER_BAR_VOLUMES_PATH (produced by
build_per_bar_volumes.py). ES 1-second closes from ES_1S_PATH. ATR(14)
Wilder is computed fresh on 5-min bars resampled from ES 1s.

Pre-reg gate (Section 6): qualitative. Print the numbers, state the reading,
STOP for user confirmation before Phase 3.
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
    ATR_WINDOW, BAR_FREQ, DELTA_RATIO, DIVISOR_FLOOR, ES_1S_PATH,
    FORWARD_RETURN_MINUTES, IS_TRADE_LOG_PATH, OOS_TRADE_LOG_PATH,
    OUTPUT_DIR, PER_BAR_VOLUMES_PATH, PHASE2_REPORT_MD, PHASE2_RESULTS_CSV,
    PRICE_ATR_MULT, PREREG_COMMIT, RTH_END, RTH_START, TIMEZONE,
    TRAILING_MEDIAN_BARS, VOLUME_MULT, WINDOW_SECONDS, load_trade_log,
    true_range, wilder_atr,
)


# ---------- DST sanity check ------------------------------------------------
def dst_sanity_check(trades: pd.DataFrame) -> str:
    """Per user requirement E. Find a trade on 2025-11-04 (post-DST-end, EST)
    and one on 2026-03-09 (post-DST-start, EDT). Print UTC + ET conversions.
    Returns a string snippet for inclusion in the report.
    """
    lines = ["## DST sanity check\n"]
    for date_str, expected_offset_label in [
        ("2025-11-04", "EST (-05:00)"),
        ("2026-03-09", "EDT (-04:00)"),
    ]:
        target = pd.Timestamp(date_str).date()
        sub = trades[trades["entry_time_et"].dt.date == target]
        if len(sub):
            row = sub.iloc[0]
            et = row["entry_time_et"]
            utc = row["entry_time_utc"]
            offset = et.utcoffset()
            line = (
                f"- {date_str} (expected {expected_offset_label}): "
                f"first trade on this date → UTC={utc.isoformat()}, "
                f"ET={et.isoformat()}, offset={offset}"
            )
        else:
            # Nearest trade
            diffs = (trades["entry_time_et"].dt.date - target).abs() \
                if False else None
            # simple linear scan
            diffs = pd.Series([(t - target).days for t in trades["entry_time_et"].dt.date]).abs()
            idx = int(diffs.idxmin())
            row = trades.iloc[idx]
            et = row["entry_time_et"]
            utc = row["entry_time_utc"]
            line = (
                f"- {date_str} (expected {expected_offset_label}): "
                f"no trade on that exact date; nearest trade {et.date()} → "
                f"UTC={utc.isoformat()}, ET={et.isoformat()}, offset={et.utcoffset()}"
            )
        print(line)
        lines.append(line)
    return "\n".join(lines) + "\n"


# ---------- main analysis ---------------------------------------------------
def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # ---- DST sanity check via trade log ----
    print("=" * 70)
    print("DST sanity check (per user requirement E)")
    print("=" * 70)
    trades = load_trade_log()
    dst_snippet = dst_sanity_check(trades)
    print()

    # ---- Load per-bar volumes ----
    print("=" * 70)
    print("Loading per-bar volumes + ES 1s bars")
    print("=" * 70)
    bv = pd.read_parquet(PER_BAR_VOLUMES_PATH)
    if not isinstance(bv["bar_close_utc"].dtype, pd.DatetimeTZDtype):
        bv["bar_close_utc"] = pd.to_datetime(bv["bar_close_utc"], utc=True)
    bv["bar_close_et"] = bv["bar_close_utc"].dt.tz_convert(TIMEZONE)
    bv["session_date"] = pd.to_datetime(bv["session_date"]).dt.date
    bv = bv.sort_values("bar_close_utc").reset_index(drop=True)
    print(f"  per_bar_volumes: {len(bv):,} bars across {bv['session_date'].nunique()} sessions")

    # ---- Trailing 100-bar median (strictly preceding via shift(1)) ----
    bv["median_buy_100"] = bv["dir_buy_vol_60s"].rolling(
        TRAILING_MEDIAN_BARS, min_periods=TRAILING_MEDIAN_BARS
    ).median().shift(1)
    bv["median_sell_100"] = bv["dir_sell_vol_60s"].rolling(
        TRAILING_MEDIAN_BARS, min_periods=TRAILING_MEDIAN_BARS
    ).median().shift(1)
    n_p2_evaluable = int(bv["median_buy_100"].notna().sum())
    print(f"  P2-evaluable bars (trailing 100 median finite): {n_p2_evaluable:,}")

    # ---- ES 1s → 5-min bars + Wilder ATR(14) ----
    es_1s = pd.read_parquet(ES_1S_PATH, columns=["open", "high", "low", "close"])
    if not isinstance(es_1s.index.dtype, pd.DatetimeTZDtype):
        es_1s.index = pd.to_datetime(es_1s.index, utc=True).tz_convert(TIMEZONE)
    print(f"  ES 1s loaded: {len(es_1s):,} rows, "
          f"{es_1s.index.min()} → {es_1s.index.max()}")

    es_5min = (
        es_1s.resample(BAR_FREQ, label="right", closed="right")
             .agg({"open": "first", "high": "max", "low": "min", "close": "last"})
             .dropna(subset=["close"])
    )
    es_5min["tr"] = true_range(es_5min["high"], es_5min["low"], es_5min["close"])
    es_5min["atr"] = wilder_atr(es_5min["tr"], ATR_WINDOW)
    print(f"  ES 5-min resampled: {len(es_5min):,} bars")

    # Join price + ATR at bar close T (use ET index)
    bv = bv.set_index("bar_close_et")
    bv["price_at_T"] = es_5min["close"].reindex(bv.index)
    bv["atr_at_T"] = es_5min["atr"].reindex(bv.index)
    bv = bv.reset_index()

    # price at T + 60s: 1-second resolution lookup with 5s tolerance (forward-fill).
    # Use DatetimeIndex (not .values) to preserve tz; otherwise the array dtype
    # diverges from es_1s.index (datetime64[ns, America/New_York]).
    target_60_idx = pd.DatetimeIndex(
        bv["bar_close_et"] + pd.Timedelta(seconds=WINDOW_SECONDS)
    )
    bv["price_at_T_plus_60"] = es_1s["close"].reindex(
        target_60_idx, method="ffill", tolerance=pd.Timedelta("5s")
    ).values

    # price at T + 25min (signed forward return): same-session check
    target_25_idx = pd.DatetimeIndex(
        bv["bar_close_et"] + pd.Timedelta(minutes=FORWARD_RETURN_MINUTES)
    )
    bv["price_at_T_plus_25min"] = es_1s["close"].reindex(
        target_25_idx, method="ffill", tolerance=pd.Timedelta("5s")
    ).values
    bv["t_plus_25min_session"] = target_25_idx.date
    same_session = bv["t_plus_25min_session"] == bv["session_date"]
    bv.loc[~same_session, "price_at_T_plus_25min"] = np.nan
    bv["fwd_ret_25min_raw"] = bv["price_at_T_plus_25min"] - bv["price_at_T"]

    # ---- Predicates per pre-reg Section 4 + Section 5 ----
    bv["p2_long"] = bv["dir_buy_vol_60s"] >= (VOLUME_MULT * bv["median_buy_100"])
    bv["p2_short"] = bv["dir_sell_vol_60s"] >= (VOLUME_MULT * bv["median_sell_100"])

    denom_long = bv["dir_sell_vol_60s"].clip(lower=DIVISOR_FLOOR)
    denom_short = bv["dir_buy_vol_60s"].clip(lower=DIVISOR_FLOOR)
    bv["delta_ratio_long"] = bv["dir_buy_vol_60s"] / denom_long
    bv["delta_ratio_short"] = bv["dir_sell_vol_60s"] / denom_short
    bv["p3_long"] = bv["delta_ratio_long"] >= DELTA_RATIO
    bv["p3_short"] = bv["delta_ratio_short"] >= DELTA_RATIO

    bv["price_move_60s"] = bv["price_at_T_plus_60"] - bv["price_at_T"]
    bv["p4_threshold"] = PRICE_ATR_MULT * bv["atr_at_T"]
    bv["p4_long"] = bv["price_move_60s"] >= bv["p4_threshold"]
    bv["p4_short"] = (-bv["price_move_60s"]) >= bv["p4_threshold"]

    # Triggers — require P2 evaluable (median finite) AND price/ATR finite
    base_eval = (
        bv["median_buy_100"].notna() & bv["median_sell_100"].notna()
        & bv["price_at_T"].notna() & bv["price_at_T_plus_60"].notna()
        & bv["atr_at_T"].notna()
    )
    bv["trcb_long"] = (bv["p2_long"] & bv["p3_long"] & bv["p4_long"]).fillna(False) & base_eval
    bv["trcb_short"] = (bv["p2_short"] & bv["p3_short"] & bv["p4_short"]).fillna(False) & base_eval

    # Signed 25-min forward return
    bv["fwd_ret_25min_signed"] = np.nan
    bv.loc[bv["trcb_long"], "fwd_ret_25min_signed"] = bv.loc[bv["trcb_long"], "fwd_ret_25min_raw"]
    bv.loc[bv["trcb_short"], "fwd_ret_25min_signed"] = -bv.loc[bv["trcb_short"], "fwd_ret_25min_raw"]

    # ---- Stats per pre-reg Section 6 ----
    print()
    print("=" * 70)
    print("PHASE 2 RESULTS")
    print("=" * 70)
    n_total_bars = len(bv)
    n_evaluable = int(base_eval.sum())
    n_long = int(bv["trcb_long"].sum())
    n_short = int(bv["trcb_short"].sum())
    n_trig = n_long + n_short
    trig_rate = n_trig / n_evaluable if n_evaluable else 0.0

    print(f"\nTotal bars in corpus               : {n_total_bars:,}")
    print(f"Fully evaluable bars (post-warmup) : {n_evaluable:,}")
    print(f"Triggered long                     : {n_long:,}")
    print(f"Triggered short                    : {n_short:,}")
    print(f"Total triggered                    : {n_trig:,}")
    print(f"Trigger rate (of evaluable)        : {trig_rate*100:.4f}%")

    # Pass counts per predicate alone
    print("\nIndividual predicate pass counts (over evaluable bars, each direction):")
    for d in ("long", "short"):
        p2 = int((bv[f"p2_{d}"] & base_eval).sum())
        p3 = int((bv[f"p3_{d}"] & base_eval).sum())
        p4 = int((bv[f"p4_{d}"] & base_eval).sum())
        p_all = int((bv[f"trcb_{d}"]).sum())
        print(f"  {d:5s}: P2={p2:,}  P3={p3:,}  P4={p4:,}  all-three={p_all:,}")

    # Triggered vs non-triggered forward returns
    trig_mask = bv["trcb_long"] | bv["trcb_short"]
    trig_ret = bv.loc[trig_mask, "fwd_ret_25min_signed"].dropna()
    untrig_mask = base_eval & (~trig_mask)
    # For untriggered: forward return without direction — use raw + absolute as reference.
    # The pre-reg only specifies signed return for triggered; unconditional baseline = raw.
    untrig_ret_raw = bv.loc[untrig_mask, "fwd_ret_25min_raw"].dropna()
    all_eval_raw = bv.loc[base_eval, "fwd_ret_25min_raw"].dropna()

    def stat_block(name: str, s: pd.Series) -> dict:
        if len(s) == 0:
            return {"name": name, "n": 0}
        return {
            "name": name, "n": len(s),
            "mean": float(s.mean()),
            "median": float(s.median()),
            "std": float(s.std(ddof=1)) if len(s) > 1 else float("nan"),
            "sum": float(s.sum()),
            "min": float(s.min()),
            "max": float(s.max()),
            "t_vs_zero": (float(s.mean() / (s.std(ddof=1) / np.sqrt(len(s))))
                           if len(s) > 1 and s.std(ddof=1) > 0 else float("nan")),
            "pct_positive": float((s > 0).mean()),
        }

    s_trig = stat_block("triggered (signed)", trig_ret)
    s_untrig_raw = stat_block("untriggered (raw, no direction)", untrig_ret_raw)
    s_all_raw = stat_block("all evaluable (raw, unconditional)", all_eval_raw)

    print("\nForward return (25-min) stats:")
    for blk in (s_trig, s_untrig_raw, s_all_raw):
        if blk.get("n", 0) == 0:
            print(f"  {blk['name']}: n=0 (empty)")
            continue
        print(f"  {blk['name']}: n={blk['n']:,}  "
              f"mean={blk['mean']:+.4f}  median={blk['median']:+.4f}  "
              f"std={blk['std']:.4f}  t={blk['t_vs_zero']:+.4f}  "
              f"%>0={blk['pct_positive']*100:.2f}%")

    # Two-sample t-test: triggered (signed) vs all evaluable (raw)
    # Note: signed vs raw is not a perfect comparison because the signed series has
    # implicit direction. Per pre-reg, we test whether triggered has directional lift.
    welch_t = float("nan")
    welch_p = float("nan")
    if len(trig_ret) >= 3 and len(all_eval_raw) >= 3:
        welch = sps.ttest_ind(trig_ret, all_eval_raw, equal_var=False, nan_policy="omit")
        welch_t = float(welch.statistic)
        welch_p = float(welch.pvalue)
    print(f"\nWelch t-test triggered (signed) vs all-eval (raw, unconditional):")
    print(f"  t={welch_t:+.4f}  p={welch_p:.6f}")

    # Per-direction breakdown
    long_ret = bv.loc[bv["trcb_long"], "fwd_ret_25min_signed"].dropna()
    short_ret = bv.loc[bv["trcb_short"], "fwd_ret_25min_signed"].dropna()
    s_long = stat_block("triggered LONG", long_ret)
    s_short = stat_block("triggered SHORT", short_ret)
    print("\nDirectional breakdown:")
    for blk in (s_long, s_short):
        if blk.get("n", 0) == 0:
            print(f"  {blk['name']}: n=0"); continue
        print(f"  {blk['name']}: n={blk['n']:,}  mean={blk['mean']:+.4f}  "
              f"t={blk['t_vs_zero']:+.4f}  %>0={blk['pct_positive']*100:.2f}%")

    # Trigger rate by hour bucket (ET)
    bv["hour_bucket"] = bv["bar_close_et"].dt.strftime("%H:%M")
    bv["hour_only"] = bv["bar_close_et"].dt.hour
    # 1-hour buckets
    print("\nTrigger rate by hour bucket (ET, on evaluable bars):")
    hour_stats_lines = []
    for h_start in range(9, 16):
        mask = base_eval & (bv["hour_only"] == h_start)
        n_b = int(mask.sum())
        n_t = int((mask & trig_mask).sum())
        rate = n_t / n_b if n_b else 0.0
        line = f"  {h_start:02d}:00–{h_start:02d}:59  evaluable={n_b:>5d}  triggers={n_t:>4d}  rate={rate*100:>6.3f}%"
        print(line)
        hour_stats_lines.append(line)

    # Day-disagreement carry-over from per_bar_volumes (already 0% across corpus)
    max_day_disagree = float(bv["day_side_disagree_rate"].max())
    n_flagged_days = int((bv.groupby("session_date")["day_side_disagree_rate"]
                          .first() > 0.02).sum())
    print(f"\nSide-vs-midpoint disagreement (carried from build_per_bar_volumes):")
    print(f"  max per-day disagreement rate: {max_day_disagree*100:.4f}%")
    print(f"  days flagged (>2%):            {n_flagged_days}")

    # ---- Verdict per pre-reg Section 6 (qualitative) ----
    print()
    print("=" * 70)
    print("VERDICT (qualitative — per pre-reg Section 6)")
    print("=" * 70)
    uncond_mean = s_all_raw["mean"] if s_all_raw.get("n", 0) else float("nan")
    trig_mean = s_trig["mean"] if s_trig.get("n", 0) else float("nan")
    print(f"  triggered signed mean    = {trig_mean:+.4f} ES points (n={s_trig.get('n',0):,})")
    print(f"  unconditional raw mean   = {uncond_mean:+.4f} ES points (n={s_all_raw.get('n',0):,})")
    print(f"  separation (trig − cond) = {trig_mean - uncond_mean:+.4f}")
    print(f"  triggered t-stat vs 0    = {s_trig.get('t_vs_zero', float('nan')):+.4f}")
    print(f"  triggered %>0            = {s_trig.get('pct_positive', 0)*100:.2f}%")
    print()
    if (trig_mean > 0 and (trig_mean - uncond_mean) > 0
            and abs(s_trig.get("t_vs_zero", 0)) >= 2.0):
        verdict_line = "READING: triggered bars show directionally positive mean signed return AND meaningful t-stat (|t|≥2)."
        verdict_reading = "Looks like PASS, but pre-reg makes this user's call."
    elif (trig_mean > 0 and (trig_mean - uncond_mean) > 0):
        verdict_line = "READING: triggered bars show directionally positive mean but t-stat below 2.0 — economic vs statistical tension."
        verdict_reading = "AMBIGUOUS — user judgment required."
    elif trig_mean <= 0:
        verdict_line = "READING: triggered bars mean is non-positive — directional signal missing or wrong sign."
        verdict_reading = "Looks like FAIL, but pre-reg makes this user's call."
    else:
        verdict_line = "READING: triggered mean similar to unconditional — no separation."
        verdict_reading = "AMBIGUOUS — user judgment required."
    print(f"  {verdict_line}")
    print(f"  {verdict_reading}")
    print()
    print("STOPPED — per pre-reg Section 6, do not auto-proceed to Phase 3.")

    # ---- Persist outputs ----
    cols_keep = [
        "bar_close_utc", "bar_close_et", "session_date",
        "dir_buy_vol_60s", "dir_sell_vol_60s", "n_trades_60s",
        "median_buy_100", "median_sell_100",
        "delta_ratio_long", "delta_ratio_short",
        "price_at_T", "price_at_T_plus_60", "price_move_60s",
        "atr_at_T", "p4_threshold",
        "p2_long", "p2_short", "p3_long", "p3_short", "p4_long", "p4_short",
        "trcb_long", "trcb_short",
        "fwd_ret_25min_raw", "fwd_ret_25min_signed",
        "day_side_disagree_rate",
    ]
    out = bv[cols_keep].copy()
    out.to_csv(PHASE2_RESULTS_CSV, index=False)
    print(f"\nSaved: {PHASE2_RESULTS_CSV}")

    # Markdown report
    md = _build_markdown_report(
        n_total_bars=n_total_bars, n_evaluable=n_evaluable,
        n_long=n_long, n_short=n_short, trig_rate=trig_rate,
        s_trig=s_trig, s_untrig=s_untrig_raw, s_all=s_all_raw,
        welch_t=welch_t, welch_p=welch_p,
        s_dir_long=s_long, s_dir_short=s_short,
        bv=bv, base_eval=base_eval, trig_mask=trig_mask,
        max_day_disagree=max_day_disagree, n_flagged_days=n_flagged_days,
        dst_snippet=dst_snippet,
        verdict_line=verdict_line, verdict_reading=verdict_reading,
        uncond_mean=uncond_mean, trig_mean=trig_mean,
    )
    PHASE2_REPORT_MD.write_text(md)
    print(f"Saved: {PHASE2_REPORT_MD}")


def _build_markdown_report(**kw) -> str:
    bv = kw["bv"]; base_eval = kw["base_eval"]; trig_mask = kw["trig_mask"]
    s_trig = kw["s_trig"]; s_untrig = kw["s_untrig"]; s_all = kw["s_all"]
    s_dl = kw["s_dir_long"]; s_ds = kw["s_dir_short"]

    parts = []
    parts.append("# TRCB-v1 Phase 2 — Population-Level Validation Report\n")
    parts.append(f"**Generated:** {datetime.now().isoformat(timespec='seconds')}")
    parts.append(f"**Pre-reg commit:** `{PREREG_COMMIT}`")
    parts.append("**Header note:** *Produced under pre-registration commit "
                 f"`{PREREG_COMMIT}`. Parameters locked (P1={WINDOW_SECONDS}s, "
                 f"P2={VOLUME_MULT}×, P3={DELTA_RATIO}:1, P4={PRICE_ATR_MULT}×ATR, "
                 f"ATR_WINDOW={ATR_WINDOW}). Not modified based on these results.*\n")

    parts.append(kw["dst_snippet"])

    parts.append("## Corpus")
    parts.append(f"- Total RTH 5-min bars: **{kw['n_total_bars']:,}**")
    parts.append(f"- Fully evaluable bars (post-100-bar warmup, finite price+ATR): **{kw['n_evaluable']:,}**")
    parts.append(f"- Sessions covered: {bv['session_date'].nunique()}")
    parts.append(f"- Date range: {bv['session_date'].min()} → {bv['session_date'].max()}\n")

    parts.append("## Trigger counts and rate")
    parts.append(f"- Triggered LONG: **{kw['n_long']:,}**")
    parts.append(f"- Triggered SHORT: **{kw['n_short']:,}**")
    parts.append(f"- Total triggered: **{kw['n_long']+kw['n_short']:,}**")
    parts.append(f"- Trigger rate over evaluable bars: **{kw['trig_rate']*100:.4f}%**\n")

    parts.append("## Per-predicate pass counts (on evaluable bars)")
    parts.append("| direction | P2 | P3 | P4 | all-three |")
    parts.append("|---|---:|---:|---:|---:|")
    for d in ("long", "short"):
        p2 = int((bv[f"p2_{d}"] & base_eval).sum())
        p3 = int((bv[f"p3_{d}"] & base_eval).sum())
        p4 = int((bv[f"p4_{d}"] & base_eval).sum())
        p_all = int(bv[f"trcb_{d}"].sum())
        parts.append(f"| {d} | {p2:,} | {p3:,} | {p4:,} | {p_all:,} |")
    parts.append("")

    parts.append("## 25-min forward return statistics")
    parts.append("| sample | n | mean | median | std | t vs 0 | % > 0 |")
    parts.append("|---|---:|---:|---:|---:|---:|---:|")
    for s in (s_trig, s_untrig, s_all):
        if s.get("n", 0) == 0:
            continue
        parts.append(
            f"| {s['name']} | {s['n']:,} | {s['mean']:+.4f} | {s['median']:+.4f} | "
            f"{s['std']:.4f} | {s['t_vs_zero']:+.4f} | {s['pct_positive']*100:.2f}% |"
        )
    parts.append("")
    parts.append(f"**Welch two-sample t-test triggered (signed) vs all-evaluable (raw):** "
                 f"t = **{kw['welch_t']:+.4f}**, p = **{kw['welch_p']:.6f}**\n")

    parts.append("## Directional breakdown (triggered, signed)")
    parts.append("| direction | n | mean | t vs 0 | % > 0 |")
    parts.append("|---|---:|---:|---:|---:|")
    for s in (s_dl, s_ds):
        if s.get("n", 0) == 0:
            continue
        parts.append(
            f"| {s['name']} | {s['n']:,} | {s['mean']:+.4f} | {s['t_vs_zero']:+.4f} | "
            f"{s['pct_positive']*100:.2f}% |"
        )
    parts.append("")

    parts.append("## Trigger rate by hour bucket (ET, evaluable bars)")
    parts.append("| hour | evaluable | triggers | rate |")
    parts.append("|---|---:|---:|---:|")
    for h_start in range(9, 16):
        mask = base_eval & (bv["hour_only"] == h_start)
        n_b = int(mask.sum())
        n_t = int((mask & trig_mask).sum())
        rate = n_t / n_b if n_b else 0.0
        parts.append(f"| {h_start:02d}:00–{h_start:02d}:59 | {n_b:,} | {n_t:,} | {rate*100:.3f}% |")
    parts.append("")

    parts.append("## Side-vs-midpoint disagreement (data integrity check)")
    parts.append(f"- Max per-day midpoint-rule-vs-Databento-`side` disagreement rate: "
                 f"**{kw['max_day_disagree']*100:.4f}%**")
    parts.append(f"- Days flagged (>2% threshold): **{kw['n_flagged_days']}**")
    parts.append("- Threshold met if zero flagged. The Databento `side` field on trade "
                 "rows is the **aggressor side** (verified empirically Step 0); the "
                 "pre-reg midpoint rule on on-row NBBO produces identical classifications "
                 "across the corpus.\n")

    parts.append("## Verdict (qualitative — per pre-reg Section 6)\n")
    parts.append(f"- Triggered signed mean = **{kw['trig_mean']:+.4f}** ES points "
                 f"(n = {s_trig.get('n', 0):,})")
    parts.append(f"- Unconditional raw mean = **{kw['uncond_mean']:+.4f}** ES points "
                 f"(n = {s_all.get('n', 0):,})")
    parts.append(f"- Separation (trig − cond) = **{kw['trig_mean']-kw['uncond_mean']:+.4f}**")
    parts.append("")
    parts.append(f"**READING:** {kw['verdict_line']}")
    parts.append(f"**{kw['verdict_reading']}**")
    parts.append("")
    parts.append("Pre-reg Section 6 specifies a qualitative gate. The numbers above are "
                 "presented as the basis for the user's PASS / FAIL / AMBIGUOUS call. "
                 "Phase 3 does not begin without explicit user confirmation that Phase 2 "
                 "passed.\n")

    return "\n".join(parts)


if __name__ == "__main__":
    main()
