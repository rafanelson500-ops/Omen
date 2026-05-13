"""Q8 — P4 post-detection diagnostic.

Q7 reported P4-alone 25m mean = +2.87 pts, but that measurement was taken
from price-at-T (signal bar close) — INCLUDING the qualifying 30-second
move that defined the trigger. This script measures forward returns and
MFE/MAE from T+30s (the moment you'd actually know P4 had fired),
stripping the already-completed qualifying portion out of the signal.

THROWAWAY DIAGNOSTIC — in-sample on consumed corpus. Read-only on
Phase 2 per-bar table and ES 1s bars. No new parameters.
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (  # noqa: E402
    ATR_WINDOW, ES_1S_PATH, OUTPUT_ANALYSIS_DIR, PHASE2_RESULTS_CSV,
    PRICE_ATR_MULT, TIMEZONE, WINDOW_SECONDS,
)

ET = ZoneInfo(TIMEZONE)
WINDOW = pd.Timedelta(minutes=25)
POST_HORIZONS_MIN = [1, 5, 15, 25]
N_UNCOND_SAMPLE = 1000
RNG_SEED = 73

OUT_MD = OUTPUT_ANALYSIS_DIR / "q8_p4_post_detection.md"

Q8_DISCLOSURE = """\
## DISCLOSURE — consumed-data corpus

This test is run on the same 160-session corpus that has been examined
multiple times across TRCB-v1, the post-mortem (Q1-Q4), TRCB-v2 Phase 2/3,
and Q6/Q7 component diagnostics. The corpus is consumed.

P4 alone showed strong-looking 25-min forward returns in Q7, but that
measurement included the qualifying 30-second move within the forward
return. This test isolates the post-detection signal.
"""


def _stat_block(arr: np.ndarray) -> dict:
    s = pd.Series(arr).dropna()
    n = len(s)
    if n == 0:
        return {"n": 0}
    std = float(s.std(ddof=1)) if n > 1 else float("nan")
    t = float(s.mean() / (std / np.sqrt(n))) if n > 1 and std > 0 else float("nan")
    return {"n": n, "mean": float(s.mean()), "median": float(s.median()),
            "std": std, "min": float(s.min()), "max": float(s.max()),
            "t": t, "pct_pos": float((s > 0).mean())}


def _path_stats(price_series: pd.Series, entry_price: float, direction: int) -> dict:
    """MFE/MAE/time-to/final on a 1s price path. direction = +1 long, -1 short."""
    if len(price_series) == 0 or pd.isna(entry_price):
        return {"mfe": np.nan, "mae": np.nan, "time_to_mfe_s": np.nan,
                "time_to_mae_s": np.nan, "final_return": np.nan, "n_obs": 0}
    elapsed = (price_series.index - price_series.index[0]).total_seconds().to_numpy()
    px = price_series.values
    signed_ret = direction * (px - entry_price)
    mfe_i = int(np.argmax(signed_ret)); mae_i = int(np.argmin(signed_ret))
    return {
        "mfe": float(signed_ret[mfe_i]),
        "mae": float(signed_ret[mae_i]),
        "time_to_mfe_s": float(elapsed[mfe_i]),
        "time_to_mae_s": float(elapsed[mae_i]),
        "final_return": float(signed_ret[-1]),
        "n_obs": len(signed_ret),
    }


def _classify(mfe: float, mae: float, final: float, window_s: float = 1500.0) -> str:
    if not all(np.isfinite(v) for v in (mfe, mae, final)):
        return "OTHER"
    return _classify_inner(mfe, mae, final, 0.0, window_s)


def _classify_with_time(mfe: float, mae: float, final: float,
                        time_to_mfe_s: float, window_s: float = 1500.0) -> str:
    return _classify_inner(mfe, mae, final, time_to_mfe_s, window_s)


def _classify_inner(mfe, mae, final, time_to_mfe_s, window_s):
    if not all(np.isfinite(v) for v in (mfe, mae, final, time_to_mfe_s)):
        return "OTHER"
    if mfe >= 1.0 and time_to_mfe_s < 0.5 * window_s and final < 0.5 * mfe:
        return "RUN_UP_THEN_FADE"
    if final > 1.0 and abs(mae) < 0.5 * final:
        return "CLEAN_WINNER"
    if mfe < 1.0 and final < -1.0:
        return "SLOW_BLEED"
    if mfe > 1.0 and abs(mae) > 1.0 and abs(final) < 0.5:
        return "CHOPPY"
    return "OTHER"


# ──────────────────────────────────────────────────────────────────────────────
def main() -> int:
    OUTPUT_ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)
    print(Q8_DISCLOSURE)
    print("=" * 72)
    print("Q8 — P4 post-detection diagnostic")
    print("=" * 72)
    print(f"  WINDOW_SECONDS = {WINDOW_SECONDS}, PRICE_ATR_MULT = {PRICE_ATR_MULT}, "
          f"ATR_WINDOW = {ATR_WINDOW}\n")

    # ---- Load Phase 2 per-bar table ----
    p2 = pd.read_csv(PHASE2_RESULTS_CSV)
    p2["bar_close_et"] = pd.to_datetime(p2["bar_close_et"], utc=True).dt.tz_convert(ET)
    base_eval = (
        p2["median_buy_100"].notna() & p2["median_sell_100"].notna()
        & p2["price_at_T"].notna() & p2["price_at_T_plus_30s"].notna()
        & p2["atr_at_T"].notna()
    )
    eval_df = p2[base_eval].copy().reset_index(drop=True)
    for c in ("p4_long", "p4_short"):
        eval_df[c] = eval_df[c].fillna(False).astype(bool)
    print(f"evaluable bars: {len(eval_df):,}")
    print(f"P4-long fires : {int(eval_df['p4_long'].sum()):,}")
    print(f"P4-short fires: {int(eval_df['p4_short'].sum()):,}")

    # ---- Build long-form P4-fire table (one row per direction-fire) ----
    long_fires = eval_df[eval_df["p4_long"]].copy()
    long_fires["direction"] = 1
    short_fires = eval_df[eval_df["p4_short"]].copy()
    short_fires["direction"] = -1
    p4_fires = pd.concat([long_fires, short_fires], ignore_index=True)
    n_p4 = len(p4_fires)
    print(f"P4 total fires: {n_p4:,}")

    # ---- Load ES 1s for path lookups ----
    es_1s = pd.read_parquet(ES_1S_PATH, columns=["close"])
    if not isinstance(es_1s.index.dtype, pd.DatetimeTZDtype):
        es_1s.index = pd.to_datetime(es_1s.index, utc=True).tz_convert(ET)
    es_1s = es_1s.sort_index()
    print(f"ES 1s rows    : {len(es_1s):,}")

    # ---- Compute T+30s prices and post-detection forward returns ----
    p4_fires["T_30_ts"] = p4_fires["bar_close_et"] + pd.Timedelta(seconds=WINDOW_SECONDS)
    p4_fires["price_at_T_30"] = es_1s["close"].reindex(
        pd.DatetimeIndex(p4_fires["T_30_ts"]),
        method="ffill", tolerance=pd.Timedelta("5s"),
    ).values
    p4_fires["qualifying_move"] = p4_fires["direction"] * (
        p4_fires["price_at_T_30"] - p4_fires["price_at_T"]
    )

    for h in POST_HORIZONS_MIN:
        target_idx = pd.DatetimeIndex(p4_fires["T_30_ts"] + pd.Timedelta(minutes=h))
        px = es_1s["close"].reindex(
            target_idx, method="ffill", tolerance=pd.Timedelta("5s"),
        ).values
        # RTH-truncate: if T_30 + h > 16:00 ET, signed return = NaN
        target_sess = pd.Series([d.date() for d in target_idx])
        bar_sess = pd.to_datetime(p4_fires["bar_close_et"]).dt.date.reset_index(drop=True)
        # Also enforce same-session
        rth_close = pd.DatetimeIndex(p4_fires["bar_close_et"]).normalize() + \
                    pd.Timedelta(hours=16)
        within_rth = pd.DatetimeIndex(target_idx) <= pd.DatetimeIndex(rth_close)
        same_sess = (target_sess == bar_sess).values
        signed = p4_fires["direction"].values * (px - p4_fires["price_at_T_30"].values)
        signed = np.where(within_rth & same_sess, signed, np.nan)
        p4_fires[f"post_ret_{h}m_signed"] = signed

    # Sanity: matching N
    n_post_finite = {h: int(p4_fires[f"post_ret_{h}m_signed"].notna().sum())
                      for h in POST_HORIZONS_MIN}
    print("post-return finite counts by horizon:", n_post_finite)

    # ---- Unconditional baseline ----
    rng = np.random.default_rng(RNG_SEED)
    sample_idx = rng.choice(len(eval_df), size=min(N_UNCOND_SAMPLE, len(eval_df)),
                             replace=False)
    uncond = eval_df.iloc[sample_idx].copy().reset_index(drop=True)
    # Half long, half short for direction balance (sign by always-long is biased)
    uncond["direction"] = np.where(rng.random(len(uncond)) < 0.5, 1, -1)
    uncond["T_30_ts"] = uncond["bar_close_et"] + pd.Timedelta(seconds=WINDOW_SECONDS)
    uncond["price_at_T_30"] = es_1s["close"].reindex(
        pd.DatetimeIndex(uncond["T_30_ts"]),
        method="ffill", tolerance=pd.Timedelta("5s"),
    ).values
    for h in POST_HORIZONS_MIN:
        target_idx = pd.DatetimeIndex(uncond["T_30_ts"] + pd.Timedelta(minutes=h))
        px = es_1s["close"].reindex(
            target_idx, method="ffill", tolerance=pd.Timedelta("5s"),
        ).values
        rth_close = pd.DatetimeIndex(uncond["bar_close_et"]).normalize() + \
                    pd.Timedelta(hours=16)
        within_rth = pd.DatetimeIndex(target_idx) <= pd.DatetimeIndex(rth_close)
        bar_sess = pd.to_datetime(uncond["bar_close_et"]).dt.date.reset_index(drop=True)
        tgt_sess = pd.Series([d.date() for d in target_idx])
        same_sess = (tgt_sess == bar_sess).values
        signed = uncond["direction"].values * (px - uncond["price_at_T_30"].values)
        signed = np.where(within_rth & same_sess, signed, np.nan)
        uncond[f"post_ret_{h}m_signed"] = signed

    # ---- Table A: post-detection forward returns ----
    print("\n" + "-" * 72)
    print("TABLE A — Post-detection forward returns (from T+30s)")
    print("-" * 72)
    print(f"  {'horizon':<8s} "
          f"{'P4 n':>7s} {'P4 mean':>10s} {'P4 t':>8s} {'P4 %+':>7s} | "
          f"{'unc n':>6s} {'unc mean':>10s} {'unc t':>8s}")
    table_A = []
    for h in POST_HORIZONS_MIN:
        p_stat = _stat_block(p4_fires[f"post_ret_{h}m_signed"].values)
        u_stat = _stat_block(uncond[f"post_ret_{h}m_signed"].values)
        print(f"  {h:>4d}m   "
              f"{p_stat['n']:>7d} {p_stat['mean']:>+10.4f} {p_stat['t']:>+8.2f} "
              f"{p_stat['pct_pos']*100:>6.2f}% | "
              f"{u_stat['n']:>6d} {u_stat['mean']:>+10.4f} {u_stat['t']:>+8.2f}")
        table_A.append({"horizon": h, "p4": p_stat, "uncond": u_stat})

    # ---- Table B: qualifying move ----
    print("\n" + "-" * 72)
    print("TABLE B — Qualifying move (signed, in points)")
    print("-" * 72)
    qm = p4_fires["qualifying_move"].dropna()
    qm_long = p4_fires.loc[p4_fires["direction"] == 1, "qualifying_move"].dropna()
    qm_short = p4_fires.loc[p4_fires["direction"] == -1, "qualifying_move"].dropna()
    def qprint(label, s):
        q = np.quantile(s.values, [0.25, 0.50, 0.75])
        print(f"  {label:<14s} n={len(s):>5d}  mean={s.mean():+.4f}  "
              f"q25={q[0]:+.4f}  q50={q[1]:+.4f}  q75={q[2]:+.4f}  "
              f"min={s.min():+.4f}  max={s.max():+.4f}")
    qprint("ALL P4-fires", qm)
    qprint("LONG fires",   qm_long)
    qprint("SHORT fires",  qm_short)

    # ---- Build per-trigger MFE/MAE paths (from T_30) ----
    print("\n" + "-" * 72)
    print("Computing MFE/MAE paths from T+30s for each P4-fire ...")
    path_stats_rows = []
    es_idx_arr = es_1s.index.to_numpy()
    es_px_arr = es_1s["close"].to_numpy()
    for i, row in p4_fires.iterrows():
        T_30 = row["T_30_ts"]; direction = int(row["direction"])
        entry_price = row["price_at_T_30"]
        if pd.isna(entry_price):
            path_stats_rows.append({"mfe": np.nan, "mae": np.nan,
                                     "time_to_mfe_s": np.nan, "time_to_mae_s": np.nan,
                                     "final_return": np.nan, "n_obs": 0,
                                     "rth_truncated": False})
            continue
        rth_close = T_30.normalize() + pd.Timedelta(hours=16)
        win_end = min(T_30 + WINDOW, rth_close)
        rth_truncated = (T_30 + WINDOW) > rth_close
        lo = np.searchsorted(es_idx_arr, T_30 + pd.Timedelta(seconds=1), side="left")
        hi = np.searchsorted(es_idx_arr, win_end, side="right")
        if hi <= lo:
            path_stats_rows.append({"mfe": np.nan, "mae": np.nan,
                                     "time_to_mfe_s": np.nan, "time_to_mae_s": np.nan,
                                     "final_return": np.nan, "n_obs": 0,
                                     "rth_truncated": rth_truncated})
            continue
        path_idx = es_1s.index[lo:hi]
        path_px = es_px_arr[lo:hi]
        elapsed = (path_idx - T_30).total_seconds().to_numpy()
        signed_ret = direction * (path_px - entry_price)
        mfe_i = int(np.argmax(signed_ret)); mae_i = int(np.argmin(signed_ret))
        path_stats_rows.append({
            "mfe": float(signed_ret[mfe_i]), "mae": float(signed_ret[mae_i]),
            "time_to_mfe_s": float(elapsed[mfe_i]),
            "time_to_mae_s": float(elapsed[mae_i]),
            "final_return": float(signed_ret[-1]),
            "n_obs": len(signed_ret), "rth_truncated": rth_truncated,
        })
    path_df = pd.DataFrame(path_stats_rows)
    p4_fires = pd.concat([p4_fires.reset_index(drop=True),
                           path_df.reset_index(drop=True)], axis=1)
    # path_classification
    p4_fires["path_class"] = [
        _classify_with_time(r.mfe, r.mae, r.final_return, r.time_to_mfe_s)
        for r in p4_fires.itertuples()
    ]
    n_truncated = int(p4_fires["rth_truncated"].sum())
    n_pathok = int(p4_fires["mfe"].notna().sum())
    print(f"  paths computed (finite): {n_pathok:,}/{n_p4:,} "
          f"(RTH-truncated: {n_truncated})")

    # ---- Unconditional MFE/MAE ----
    print("Computing unconditional MFE/MAE paths ...")
    unc_path_rows = []
    for _, row in uncond.iterrows():
        T_30 = row["T_30_ts"]; direction = int(row["direction"])
        entry_price = row["price_at_T_30"]
        if pd.isna(entry_price):
            unc_path_rows.append({"mfe": np.nan, "mae": np.nan,
                                   "time_to_mfe_s": np.nan, "time_to_mae_s": np.nan,
                                   "final_return": np.nan, "rth_truncated": False})
            continue
        rth_close = T_30.normalize() + pd.Timedelta(hours=16)
        win_end = min(T_30 + WINDOW, rth_close)
        rth_truncated = (T_30 + WINDOW) > rth_close
        lo = np.searchsorted(es_idx_arr, T_30 + pd.Timedelta(seconds=1), side="left")
        hi = np.searchsorted(es_idx_arr, win_end, side="right")
        if hi <= lo:
            unc_path_rows.append({"mfe": np.nan, "mae": np.nan,
                                   "time_to_mfe_s": np.nan, "time_to_mae_s": np.nan,
                                   "final_return": np.nan, "rth_truncated": rth_truncated})
            continue
        path_idx = es_1s.index[lo:hi]
        path_px = es_px_arr[lo:hi]
        elapsed = (path_idx - T_30).total_seconds().to_numpy()
        signed_ret = direction * (path_px - entry_price)
        mfe_i = int(np.argmax(signed_ret)); mae_i = int(np.argmin(signed_ret))
        unc_path_rows.append({
            "mfe": float(signed_ret[mfe_i]), "mae": float(signed_ret[mae_i]),
            "time_to_mfe_s": float(elapsed[mfe_i]),
            "time_to_mae_s": float(elapsed[mae_i]),
            "final_return": float(signed_ret[-1]),
            "rth_truncated": rth_truncated,
        })
    uncond = pd.concat([uncond.reset_index(drop=True),
                         pd.DataFrame(unc_path_rows).reset_index(drop=True)], axis=1)
    uncond["path_class"] = [
        _classify_with_time(r.mfe, r.mae, r.final_return, r.time_to_mfe_s)
        for r in uncond.itertuples()
    ]

    # ---- Print MFE/MAE summary ----
    def mfe_block(df, label):
        v = df.dropna(subset=["mfe"])
        return {
            "label": label, "n": len(v),
            "mfe_mean": float(v["mfe"].mean()), "mfe_median": float(v["mfe"].median()),
            "mfe_std": float(v["mfe"].std(ddof=1)),
            "mae_mean": float(v["mae"].mean()), "mae_median": float(v["mae"].median()),
            "mae_std": float(v["mae"].std(ddof=1)),
            "ttm_mean": float(v["time_to_mfe_s"].mean()),
            "ttm_median": float(v["time_to_mfe_s"].median()),
            "ttma_mean": float(v["time_to_mae_s"].mean()),
            "final_mean": float(v["final_return"].mean()),
            "giveback_mean": float((v["mfe"] - v["final_return"]).mean()),
            "rr_median": float((v["mfe"] / v["mae"].abs().replace(0, np.nan)).median()),
        }

    p4_mfe_all = mfe_block(p4_fires, "P4 all")
    p4_mfe_long = mfe_block(p4_fires[p4_fires["direction"] == 1], "P4 long")
    p4_mfe_short = mfe_block(p4_fires[p4_fires["direction"] == -1], "P4 short")
    unc_mfe = mfe_block(uncond, "unconditional (random 1k)")

    print("\n" + "-" * 72)
    print("TABLE C+D+F — MFE/MAE on P4-fires + unconditional")
    print("-" * 72)
    for blk in (p4_mfe_all, p4_mfe_long, p4_mfe_short, unc_mfe):
        print(f"\n  {blk['label']} (n={blk['n']:,}):")
        print(f"    MFE     mean={blk['mfe_mean']:+.3f}  median={blk['mfe_median']:+.3f}  "
              f"std={blk['mfe_std']:.3f}")
        print(f"    MAE     mean={blk['mae_mean']:+.3f}  median={blk['mae_median']:+.3f}  "
              f"std={blk['mae_std']:.3f}")
        print(f"    t→MFE   mean={blk['ttm_mean']:.0f}s ({blk['ttm_mean']/1500*100:.1f}% of win)  "
              f"median={blk['ttm_median']:.0f}s")
        print(f"    t→MAE   mean={blk['ttma_mean']:.0f}s")
        print(f"    final   mean={blk['final_mean']:+.3f}")
        print(f"    giveback mean (MFE - final): {blk['giveback_mean']:+.3f}")
        print(f"    MFE/|MAE| median: {blk['rr_median']:.3f}")

    # ---- Table E: path-shape classification ----
    print("\n" + "-" * 72)
    print("TABLE E — Path-shape classification")
    print("-" * 72)
    def class_table(df, label):
        sub = df.dropna(subset=["mfe"])
        counts = sub["path_class"].value_counts()
        print(f"\n  {label} (n={len(sub)}):")
        for c in ("RUN_UP_THEN_FADE", "CLEAN_WINNER", "SLOW_BLEED", "CHOPPY", "OTHER"):
            n = int(counts.get(c, 0))
            pct = 100.0 * n / max(len(sub), 1)
            print(f"    {c:<18s} {n:>6d}  ({pct:5.1f}%)")
        return {c: int(counts.get(c, 0)) for c in
                 ("RUN_UP_THEN_FADE", "CLEAN_WINNER", "SLOW_BLEED", "CHOPPY", "OTHER")}
    cls_all = class_table(p4_fires, "P4 all-fires")
    cls_long = class_table(p4_fires[p4_fires["direction"] == 1], "P4 long-fires")
    cls_short = class_table(p4_fires[p4_fires["direction"] == -1], "P4 short-fires")
    cls_unc = class_table(uncond, "unconditional (random 1k)")

    # ---- Build markdown report ----
    md = _build_md(
        table_A=table_A, qm_all=qm, qm_long=qm_long, qm_short=qm_short,
        mfe_all=p4_mfe_all, mfe_long=p4_mfe_long, mfe_short=p4_mfe_short,
        mfe_unc=unc_mfe,
        cls_all=cls_all, cls_long=cls_long, cls_short=cls_short, cls_unc=cls_unc,
        n_eval=len(eval_df), n_p4=n_p4, n_truncated=n_truncated,
    )
    OUT_MD.write_text(md)
    print(f"\n[Q8] report written: {OUT_MD}")
    return 0


# ──────────────────────────────────────────────────────────────────────────────
def _build_md(**kw) -> str:
    L: list[str] = []
    L.append("# Q8 — P4 post-detection diagnostic\n")
    L.append("Branch: `analysis/trcb-v2-consumed-data-test-throwaway` "
             "(throwaway / archive only).")
    L.append(f"Generated: {datetime.now().isoformat(timespec='seconds')}\n")
    L.append("## 1. Disclosure\n")
    L.append(Q8_DISCLOSURE)
    L.append("")

    # Setup
    L.append("## 2. Setup\n")
    L.append(f"- Locked params: WINDOW={WINDOW_SECONDS}s, PRICE_ATR_MULT={PRICE_ATR_MULT}, "
             f"ATR={ATR_WINDOW}")
    L.append(f"- Evaluable bars: {kw['n_eval']:,}")
    L.append(f"- P4 total fires (long + short): **{kw['n_p4']:,}**")
    L.append("- Reference points: T = signal bar close. T+30s = the moment P4 ")
    L.append("  detection becomes available. All Q8 forward returns and MFE/MAE are ")
    L.append("  measured from T+30s (not T) — stripping the qualifying 30s move ")
    L.append("  out of the measurement.")
    L.append(f"- Unconditional baseline: {N_UNCOND_SAMPLE} random evaluable bars with ")
    L.append("  direction randomized 50/50 (so the baseline is direction-balanced like ")
    L.append("  the P4 sample).")
    L.append(f"- RTH-truncated P4 fires (T+30s+25min would cross 16:00 ET): "
             f"{kw['n_truncated']}")
    L.append("")

    # Table A
    L.append("## 3. Tables\n")
    L.append("### Table A — Post-detection forward returns (from T+30s)\n")
    L.append("Signed by P4-fire direction (long-fires use +1, short-fires use −1). ")
    L.append("Unconditional row uses randomized direction.\n")
    L.append("| horizon (post-T+30s) | P4 n | P4 mean (pts) | P4 t | P4 % > 0 | "
             "uncond n | uncond mean | uncond t |")
    L.append("|---|---:|---:|---:|---:|---:|---:|---:|")
    for row in kw["table_A"]:
        h = row["horizon"]; p = row["p4"]; u = row["uncond"]
        L.append(f"| +{h} min | {p['n']:,} | {p['mean']:+.4f} | {p['t']:+.2f} | "
                 f"{p['pct_pos']*100:.2f}% | {u['n']} | {u['mean']:+.4f} | {u['t']:+.2f} |")
    L.append("")

    # Table B
    L.append("### Table B — Qualifying move (already-completed portion, signed by direction)\n")
    L.append("This is the move INSIDE the qualifying 30s that defined the P4 trigger. ")
    L.append("It is part of Q7's forward-return measurement but is excluded from Q8's.\n")
    L.append("| sample | n | mean (pts) | q25 | q50 | q75 | min | max |")
    L.append("|---|---:|---:|---:|---:|---:|---:|---:|")
    for label, s in (("All P4-fires", kw["qm_all"]),
                      ("Long fires",   kw["qm_long"]),
                      ("Short fires",  kw["qm_short"])):
        q = np.quantile(s.values, [0.25, 0.50, 0.75])
        L.append(f"| {label} | {len(s):,} | {s.mean():+.4f} | "
                 f"{q[0]:+.4f} | {q[1]:+.4f} | {q[2]:+.4f} | "
                 f"{s.min():+.4f} | {s.max():+.4f} |")
    L.append("")

    # Table C+D+F combined
    L.append("### Tables C, D, F — MFE/MAE on P4-fires (vs unconditional)\n")
    L.append("All measured from T+30s over a 25-minute post-detection window. ")
    L.append("Direction-signed (long fires use +1, short fires use −1; unconditional ")
    L.append("uses random 50/50 direction).\n")
    L.append("| sample | n | MFE mean | MFE median | MAE mean | MAE median | t→MFE mean (s, %win) | final mean | giveback mean | MFE/\\|MAE\\| median |")
    L.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for blk in (kw["mfe_all"], kw["mfe_long"], kw["mfe_short"], kw["mfe_unc"]):
        L.append(f"| {blk['label']} | {blk['n']:,} | "
                 f"{blk['mfe_mean']:+.3f} | {blk['mfe_median']:+.3f} | "
                 f"{blk['mae_mean']:+.3f} | {blk['mae_median']:+.3f} | "
                 f"{blk['ttm_mean']:.0f}s ({blk['ttm_mean']/1500*100:.1f}%) | "
                 f"{blk['final_mean']:+.3f} | {blk['giveback_mean']:+.3f} | "
                 f"{blk['rr_median']:.3f} |")
    L.append("")

    # Table E
    L.append("### Table E — Path-shape classification (counts and %)\n")
    L.append("Per Q4 scheme. Applied in order; first match wins. ")
    L.append("`RUN_UP_THEN_FADE`: MFE ≥ 1.0 AND t→MFE < 12.5min AND final < 0.5·MFE. ")
    L.append("`CLEAN_WINNER`: final > 1.0 AND |MAE| < 0.5·final. ")
    L.append("`SLOW_BLEED`: MFE < 1.0 AND final < −1.0. ")
    L.append("`CHOPPY`: MFE > 1.0 AND |MAE| > 1.0 AND |final| < 0.5. ")
    L.append("`OTHER`: anything else.\n")
    L.append("| sample | RUN_UP_THEN_FADE | CLEAN_WINNER | SLOW_BLEED | CHOPPY | OTHER |")
    L.append("|---|---:|---:|---:|---:|---:|")
    for label, c, total_block in (
        ("P4 all", kw["cls_all"], kw["mfe_all"]),
        ("P4 long", kw["cls_long"], kw["mfe_long"]),
        ("P4 short", kw["cls_short"], kw["mfe_short"]),
        ("unconditional", kw["cls_unc"], kw["mfe_unc"]),
    ):
        tot = max(total_block["n"], 1)
        L.append(f"| {label} (n={total_block['n']:,}) | "
                 f"{c['RUN_UP_THEN_FADE']} ({100.0*c['RUN_UP_THEN_FADE']/tot:.1f}%) | "
                 f"{c['CLEAN_WINNER']} ({100.0*c['CLEAN_WINNER']/tot:.1f}%) | "
                 f"{c['SLOW_BLEED']} ({100.0*c['SLOW_BLEED']/tot:.1f}%) | "
                 f"{c['CHOPPY']} ({100.0*c['CHOPPY']/tot:.1f}%) | "
                 f"{c['OTHER']} ({100.0*c['OTHER']/tot:.1f}%) |")
    L.append("")

    # ---- 4. Honest comparison to Q7 ----
    L.append("## 4. Honest comparison to Q7\n")
    # Pull Q7 25m mean from the bucket-summary CSV (P4 alone)
    q7_csv = OUTPUT_ANALYSIS_DIR / "q7_bucket_summary.csv"
    q7_p4_25m = None
    if q7_csv.exists():
        q7 = pd.read_csv(q7_csv)
        row = q7[q7["bucket"] == "P4 alone"]
        if len(row):
            q7_p4_25m = float(row["25m_mean"].iloc[0])

    q8_25m_p4 = kw["table_A"][-1]["p4"]["mean"]   # last entry is the 25m row
    q8_25m_uncond = kw["table_A"][-1]["uncond"]["mean"]
    qm_mean = kw["qm_all"].mean()

    L.append(f"- **Q7 reported P4-alone 25m mean** (from T): "
             f"{q7_p4_25m:+.4f} pts." if q7_p4_25m is not None else
             "- Q7 P4-alone 25m mean: (not found)")
    L.append(f"- **Q8 post-detection 25m mean** (from T+30s): {q8_25m_p4:+.4f} pts.")
    L.append(f"- **Mean qualifying 30s move**: {qm_mean:+.4f} pts.")
    if q7_p4_25m is not None:
        L.append(f"- Sanity check: Q8 + qualifying ≈ Q7 → "
                 f"{q8_25m_p4:+.4f} + {qm_mean:+.4f} = "
                 f"{q8_25m_p4 + qm_mean:+.4f} (Q7 reported {q7_p4_25m:+.4f}).")
    L.append("")
    L.append(f"- **Unconditional 25m baseline** (random direction, random bar): "
             f"{q8_25m_uncond:+.4f} pts.")
    L.append(f"- **Post-detection edge vs unconditional**: "
             f"{q8_25m_p4 - q8_25m_uncond:+.4f} pts.")
    L.append("")
    if abs(qm_mean) > 0.5 * abs(q7_p4_25m if q7_p4_25m else 1.0):
        L.append("**Reading**: the qualifying move accounts for a substantial share of Q7's ")
        L.append("apparent 25m edge. Stripping it out reveals the *pure forward* signal — ")
        L.append("which is the relevant quantity for any deployable strategy, because the ")
        L.append("qualifying move has already happened by the time you detect P4.")
    L.append("")

    # ---- 5. MFE/MAE interpretation ----
    L.append("## 5. MFE/MAE interpretation\n")
    p4_all = kw["mfe_all"]; uncond_blk = kw["mfe_unc"]
    L.append(f"- **Average run-up (P4-all MFE mean)**: {p4_all['mfe_mean']:+.3f} pts in the ")
    L.append(f"  25-min post-detection window. Median MFE: {p4_all['mfe_median']:+.3f} pts.")
    L.append(f"- **Where does MFE occur?** Mean t→MFE = {p4_all['ttm_mean']:.0f}s = "
             f"{p4_all['ttm_mean']/60:.1f} min ({p4_all['ttm_mean']/1500*100:.1f}% of window). ")
    L.append(f"  Median t→MFE = {p4_all['ttm_median']:.0f}s.")
    L.append(f"- **Giveback** (MFE − final_return): mean = {p4_all['giveback_mean']:+.3f} pts. ")
    L.append("  Large giveback signals RUN_UP_THEN_FADE pattern dominance.")
    L.append(f"- **MFE/|MAE| ratio** median: {p4_all['rr_median']:.3f}. "
             "Values ≈ 1 mean symmetric paths; > 1 means favorable-tail asymmetry.")
    L.append("")
    L.append("### Comparison vs unconditional baseline\n")
    L.append("| metric | P4 all | unconditional | ratio (P4/unc) |")
    L.append("|---|---:|---:|---:|")
    for k_label, k_p4, k_unc in (
        ("MFE mean (pts)",       p4_all["mfe_mean"],       uncond_blk["mfe_mean"]),
        ("|MAE| mean (pts)",     abs(p4_all["mae_mean"]),  abs(uncond_blk["mae_mean"])),
        ("final_return mean",    p4_all["final_mean"],     uncond_blk["final_mean"]),
        ("giveback mean",        p4_all["giveback_mean"],  uncond_blk["giveback_mean"]),
        ("t→MFE mean (s)",       p4_all["ttm_mean"],       uncond_blk["ttm_mean"]),
    ):
        ratio = (k_p4 / k_unc) if abs(k_unc) > 1e-9 else float("nan")
        L.append(f"| {k_label} | {k_p4:+.3f} | {k_unc:+.3f} | {ratio:.3f}× |")
    L.append("")
    p4_minus_unc_mfe = p4_all["mfe_mean"] - uncond_blk["mfe_mean"]
    L.append(f"P4-fire bars produce **{p4_minus_unc_mfe:+.2f} pts of MFE** above what a ")
    L.append("random direction-signed bar produces in a comparable post-T+30s window. ")
    L.append("Random bars also produce MFE — this is the volatility floor — and the ")
    L.append("question is whether P4's MFE is *meaningfully* above that floor.")
    L.append("")

    # ---- 6. Comparison to Q4 ----
    L.append("## 6. Comparison to Q4 (n=27 TRCB-v1 triggers)\n")
    L.append("Q4 measured MFE/MAE on the 27 TRCB-v1 triggers from a different parameter set ")
    L.append("(60s window, 2.0:1 ratio). Q8 measures it on ~3,200 P4-fires from a single ")
    L.append("predicate of the v2 set — a 100× larger sample.\n")
    L.append(f"- **Q4 modal shape**: RUN_UP_THEN_FADE (14/27 = 51.9% of triggers)")
    L.append(f"- **Q8 modal shape, P4 all**: "
             f"{max(kw['cls_all'], key=kw['cls_all'].get)} "
             f"({kw['cls_all'][max(kw['cls_all'], key=kw['cls_all'].get)]}/{p4_all['n']} = "
             f"{100.0*kw['cls_all'][max(kw['cls_all'], key=kw['cls_all'].get)]/max(p4_all['n'],1):.1f}%)")
    L.append(f"- **Q8 modal shape, unconditional**: "
             f"{max(kw['cls_unc'], key=kw['cls_unc'].get)} "
             f"({kw['cls_unc'][max(kw['cls_unc'], key=kw['cls_unc'].get)]}/{uncond_blk['n']} = "
             f"{100.0*kw['cls_unc'][max(kw['cls_unc'], key=kw['cls_unc'].get)]/max(uncond_blk['n'],1):.1f}%)")
    L.append("")
    L.append("If P4-all and unconditional have the **same** modal shape, the path-shape ")
    L.append("pattern is a property of 25-min ES windows generally, not a property of ")
    L.append("P4-fires specifically. If they differ, P4 selects for a different path shape.")
    L.append("")
    L.append("Q4's RUN_UP_THEN_FADE was the modal shape, *but the threshold definition is ")
    L.append("specifically tuned to catch 'price moves then fades'* — so seeing it as the ")
    L.append("mode is partly an artifact of the classification rule. Use Q8's same-rule ")
    L.append("comparison on unconditional bars as the calibration.")
    L.append("")

    # ---- 7. Implications ----
    L.append("## 7. Implications\n")
    edge_25m = q8_25m_p4 - q8_25m_uncond
    if edge_25m >= 2.0:
        L.append(f"- **Post-detection 25m edge** ({edge_25m:+.2f} pts above unconditional) ")
        L.append("  is large by ES-microstructure standards. P4 *may* carry real predictive ")
        L.append("  information beyond the qualifying move. **Worth forward-testing.**")
    elif edge_25m >= 0.5:
        L.append(f"- **Post-detection 25m edge** ({edge_25m:+.2f} pts above unconditional) ")
        L.append("  is moderate. Combined with the favorable MFE/giveback pattern, P4 ")
        L.append("  retains a non-trivial signal that decays slowly through 25 min. ")
        L.append("  Could survive forward testing.")
    elif edge_25m >= -0.2:
        L.append(f"- **Post-detection 25m edge** ({edge_25m:+.2f} pts above unconditional) ")
        L.append("  is near zero. Q7's apparent +2.87 pt 25m mean was almost entirely the ")
        L.append("  qualifying 30s move accounting for itself. No real predictive edge ")
        L.append("  for OMEN-style holds.")
    else:
        L.append(f"- **Post-detection 25m edge** ({edge_25m:+.2f} pts above unconditional) ")
        L.append("  is NEGATIVE. P4 fires actually under-perform random bars on a 25-min ")
        L.append("  forward basis — the qualifying move is followed by reversion in this ")
        L.append("  corpus.")
    L.append("")
    # MFE interpretation
    if p4_all["mfe_mean"] > 2.0 and (p4_all["mfe_mean"] - uncond_blk["mfe_mean"]) > 1.0:
        L.append(f"- **MFE is meaningfully larger** on P4-fires (mean {p4_all['mfe_mean']:+.2f} ")
        L.append(f"  pts) than on random bars ({uncond_blk['mfe_mean']:+.2f} pts). P4-fires ")
        L.append("  produce favorable run-up paths beyond what natural volatility gives you. ")
        L.append("  If a strategy could exit *at the favorable peak* it would harvest ")
        L.append(f"  ~{p4_all['mfe_mean']:.1f} pts on average — but the OMEN-style 25-min ")
        L.append(f"  hold gives back {p4_all['giveback_mean']:+.2f} pts on average.")
    elif p4_all["mfe_mean"] > 1.0:
        L.append(f"- **MFE on P4-fires** ({p4_all['mfe_mean']:+.2f} pts) is comparable to ")
        L.append(f"  unconditional ({uncond_blk['mfe_mean']:+.2f} pts). The 'run-up' is just ")
        L.append("  natural volatility — not P4-specific information.")
    L.append("")

    # ---- 8. Caveats ----
    L.append("## 8. Caveats\n")
    L.append("- **In-sample on consumed corpus**: TRCB-v1 Phase 2, Q1-Q4 post-mortem, ")
    L.append("  TRCB-v2 Phase 2/3, Q6, Q7 have all read this 160-session corpus.")
    L.append("- **P4 is partly a momentum indicator**: by construction it fires when price ")
    L.append("  already moved ≥0.25×ATR in 30s. Any MFE pattern may reflect short-horizon ")
    L.append("  momentum autocorrelation that is not stably exploitable.")
    L.append("- **Direction-balanced unconditional baseline**: random direction 50/50 cancels ")
    L.append("  drift but the unconditional MFE/MAE still reflect ES intraday volatility on ")
    L.append("  this corpus. A different period might give different baselines.")
    L.append("- **MFE/giveback is an upper bound, not realizable PnL**: 'mean MFE' requires ")
    L.append("  perfect exit timing. A real exit rule (target/stop/time) will capture only a ")
    L.append("  fraction of MFE on the winners.")
    L.append("- **Forward-test on fresh sessions required** before any conclusion about ")
    L.append("  whether P4 is a real or curve-fit edge. This corpus is consumed.")
    L.append("")
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
