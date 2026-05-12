"""TRCB-v1 post-mortem Q2 — window length sensitivity.

Re-stream MBP-10 once with 4 window lengths (30s, 60s, 120s, 300s post
each 5-min bar close). For each window, evaluate the simplified P2/P3/P4
predicates with the SAME locked parameter values (only window varies).
Compare trigger counts + 25-min forward returns across windows.

No parameter hunting beyond these four windows. Descriptive only.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path("/Users/rafanelson/Omen")
MBP10_DIR = Path("/Users/rafanelson/Library/Caches/omen-pipeline-synthesis/mbp10_cache")
ES_1S_PATH = REPO / "backend/data/market/ES_c_0_ohlcv1s_2025-09-08_2026-04-27.parquet"
OUT_DIR = REPO / "analysis/trcb-postmortem"
OUT_MULTIWIN_PARQUET = REPO / "analysis/trcb-postmortem/per_bar_volumes_multiwindow.parquet"
OUT_MD = OUT_DIR / "q2_window_lengths.md"

# Reuse classify_trades helper + bar grid via the trcb_filter common module
sys.path.insert(0, str(REPO / "scripts/trcb_filter"))
from common import (  # noqa: E402
    ATR_WINDOW, DELTA_RATIO, DIVISOR_FLOOR, FORWARD_RETURN_MINUTES,
    PRICE_ATR_MULT, TIMEZONE, TRAILING_MEDIAN_BARS, VOLUME_MULT,
    classify_trades, rth_5min_bar_closes, true_range, wilder_atr,
)

WINDOWS_S = [30, 60, 120, 300]
NEEDED_COLS = [
    "ts_event", "action", "side", "price", "size", "bid_px_00", "ask_px_00",
]


def process_day(parquet_path: Path) -> pd.DataFrame:
    """Per-day per-bar volumes across all 4 windows. Returns DataFrame with
    columns:
      bar_close_utc, session_date,
      buy_vol_{w}s, sell_vol_{w}s, n_trades_{w}s  for w in WINDOWS_S
    """
    raw = pd.read_parquet(parquet_path, columns=NEEDED_COLS)
    if not isinstance(raw["ts_event"].dtype, pd.DatetimeTZDtype):
        raw["ts_event"] = pd.to_datetime(raw["ts_event"], utc=True)
    trades = raw.loc[raw["action"] == "T"].copy()
    sess_date = pd.Timestamp(parquet_path.stem.replace("front_month_", "")).date()
    if trades.empty:
        return _empty_day(sess_date)

    trades = classify_trades(trades).sort_values("ts_event")
    ts_arr = trades["ts_event"].values.astype("datetime64[ns]")
    size_arr = trades["size"].astype("int64").values
    is_buy = trades["is_buy"].values
    is_sell = trades["is_sell"].values

    bar_closes_et = rth_5min_bar_closes(sess_date)
    bar_closes_utc = bar_closes_et.tz_convert("UTC")

    rows = []
    for t_utc in bar_closes_utc:
        t_ns = np.datetime64(t_utc.tz_convert("UTC").tz_localize(None), "ns")
        row = {"bar_close_utc": t_utc, "session_date": sess_date}
        # Use a single searchsorted for left edge; reuse for each window's right edge.
        lo = np.searchsorted(ts_arr, t_ns, side="left")
        for w in WINDOWS_S:
            end_ns = t_ns + np.timedelta64(w, "s")
            hi = np.searchsorted(ts_arr, end_ns, side="left")
            if hi <= lo:
                row[f"buy_vol_{w}s"] = 0
                row[f"sell_vol_{w}s"] = 0
                row[f"n_trades_{w}s"] = 0
                continue
            sl_size = size_arr[lo:hi]
            sl_buy = is_buy[lo:hi]
            sl_sell = is_sell[lo:hi]
            row[f"buy_vol_{w}s"] = int(sl_size[sl_buy].sum())
            row[f"sell_vol_{w}s"] = int(sl_size[sl_sell].sum())
            row[f"n_trades_{w}s"] = int(hi - lo)
        rows.append(row)
    return pd.DataFrame(rows)


def _empty_day(sess_date) -> pd.DataFrame:
    bar_closes_et = rth_5min_bar_closes(sess_date)
    base = {"bar_close_utc": bar_closes_et.tz_convert("UTC"),
            "session_date": [sess_date] * len(bar_closes_et)}
    for w in WINDOWS_S:
        base[f"buy_vol_{w}s"] = 0
        base[f"sell_vol_{w}s"] = 0
        base[f"n_trades_{w}s"] = 0
    return pd.DataFrame(base)


def build_or_load() -> pd.DataFrame:
    if OUT_MULTIWIN_PARQUET.exists():
        print(f"Resume: loading existing {OUT_MULTIWIN_PARQUET}")
        return pd.read_parquet(OUT_MULTIWIN_PARQUET)

    files = sorted(MBP10_DIR.glob("front_month_*.parquet"))
    print(f"Streaming {len(files)} MBP-10 days with windows {WINDOWS_S}…")
    dfs = []
    t0 = time.time()
    for i, p in enumerate(files, 1):
        td = time.time()
        df = process_day(p)
        elapsed = time.time() - td
        dfs.append(df)
        if i % 20 == 0 or i <= 3:
            print(f"  [{i:>3d}/{len(files)}] {p.stem}  bars={len(df)}  ({elapsed:.2f}s)")
    out = pd.concat(dfs, ignore_index=True)
    out = out.sort_values("bar_close_utc").reset_index(drop=True)
    OUT_MULTIWIN_PARQUET.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(OUT_MULTIWIN_PARQUET, index=False)
    print(f"Saved: {OUT_MULTIWIN_PARQUET}  ({len(out):,} bars, "
          f"{(time.time()-t0)/60:.1f} min total)")
    return out


def evaluate_window(bv: pd.DataFrame, w: int, es_1s: pd.Series, atr_5min: pd.Series,
                   raw_close_5min: pd.Series) -> dict:
    """Evaluate the simplified TRCB filter for a given window length w (sec).

    Returns stats dict.
    """
    df = bv.copy()
    df["bar_close_et"] = df["bar_close_utc"].dt.tz_convert(TIMEZONE)
    df = df.set_index("bar_close_et", drop=False).sort_index()

    buy_col = f"buy_vol_{w}s"
    sell_col = f"sell_vol_{w}s"

    # Trailing 100-bar median (strictly preceding via shift(1))
    df["median_buy_100"] = df[buy_col].rolling(
        TRAILING_MEDIAN_BARS, min_periods=TRAILING_MEDIAN_BARS
    ).median().shift(1)
    df["median_sell_100"] = df[sell_col].rolling(
        TRAILING_MEDIAN_BARS, min_periods=TRAILING_MEDIAN_BARS
    ).median().shift(1)

    # price at T (use 5-min bar close, aligned with bar_close_et)
    df["price_at_T"] = raw_close_5min.reindex(df.index)
    df["atr_at_T"] = atr_5min.reindex(df.index)

    # price at T + w seconds (1s lookup)
    target_w_idx = pd.DatetimeIndex(df.index + pd.Timedelta(seconds=w))
    df["price_at_T_plus_w"] = es_1s.reindex(target_w_idx, method="ffill",
                                            tolerance=pd.Timedelta("5s")).values
    df["price_move"] = df["price_at_T_plus_w"] - df["price_at_T"]
    df["p4_threshold"] = PRICE_ATR_MULT * df["atr_at_T"]

    # 25-min forward return (same for all windows; signed by direction)
    target_25_idx = pd.DatetimeIndex(df.index + pd.Timedelta(minutes=FORWARD_RETURN_MINUTES))
    df["price_at_T_plus_25"] = es_1s.reindex(target_25_idx, method="ffill",
                                            tolerance=pd.Timedelta("5s")).values
    same_session = pd.Series(target_25_idx.date, index=df.index) == df["session_date"]
    df.loc[~same_session, "price_at_T_plus_25"] = np.nan
    df["fwd_ret_25_raw"] = df["price_at_T_plus_25"] - df["price_at_T"]

    # Predicates
    df["p2_long"] = df[buy_col] >= (VOLUME_MULT * df["median_buy_100"])
    df["p2_short"] = df[sell_col] >= (VOLUME_MULT * df["median_sell_100"])
    denom_long = df[sell_col].clip(lower=DIVISOR_FLOOR)
    denom_short = df[buy_col].clip(lower=DIVISOR_FLOOR)
    df["p3_long"] = df[buy_col] / denom_long >= DELTA_RATIO
    df["p3_short"] = df[sell_col] / denom_short >= DELTA_RATIO
    df["p4_long"] = df["price_move"] >= df["p4_threshold"]
    df["p4_short"] = (-df["price_move"]) >= df["p4_threshold"]

    base_eval = (
        df["median_buy_100"].notna() & df["median_sell_100"].notna()
        & df["price_at_T"].notna() & df["price_at_T_plus_w"].notna()
        & df["atr_at_T"].notna()
    )
    df["trcb_long"] = (df["p2_long"] & df["p3_long"] & df["p4_long"]).fillna(False) & base_eval
    df["trcb_short"] = (df["p2_short"] & df["p3_short"] & df["p4_short"]).fillna(False) & base_eval

    df["fwd_ret_25_signed"] = np.nan
    df.loc[df["trcb_long"], "fwd_ret_25_signed"] = df.loc[df["trcb_long"], "fwd_ret_25_raw"]
    df.loc[df["trcb_short"], "fwd_ret_25_signed"] = -df.loc[df["trcb_short"], "fwd_ret_25_raw"]

    n_long = int(df["trcb_long"].sum())
    n_short = int(df["trcb_short"].sum())
    n_trig = n_long + n_short
    n_eval = int(base_eval.sum())
    trig_ret = df.loc[df["trcb_long"] | df["trcb_short"], "fwd_ret_25_signed"].dropna()
    uncond = df.loc[base_eval, "fwd_ret_25_raw"].dropna()

    if len(trig_ret) >= 2:
        mean_t = float(trig_ret.mean())
        std_t = float(trig_ret.std(ddof=1)) if len(trig_ret) > 1 else float("nan")
        t_stat = float(mean_t / (std_t / np.sqrt(len(trig_ret)))) if std_t > 0 else float("nan")
    else:
        mean_t = float("nan")
        t_stat = float("nan")
    mean_u = float(uncond.mean()) if len(uncond) else float("nan")
    sep = (mean_t - mean_u) if (not np.isnan(mean_t) and not np.isnan(mean_u)) else float("nan")

    return {
        "window_s": w,
        "n_eval": n_eval,
        "n_long": n_long, "n_short": n_short, "n_trig": n_trig,
        "trig_rate_pct": n_trig / n_eval * 100 if n_eval else float("nan"),
        "mean_fwd_signed": mean_t,
        "t_stat": t_stat,
        "uncond_mean": mean_u,
        "sep_vs_uncond": sep,
        "pct_pos_trig": float((trig_ret > 0).mean() * 100) if len(trig_ret) else float("nan"),
    }


def main() -> None:
    bv = build_or_load()
    if not isinstance(bv["bar_close_utc"].dtype, pd.DatetimeTZDtype):
        bv["bar_close_utc"] = pd.to_datetime(bv["bar_close_utc"], utc=True)
    bv["session_date"] = pd.to_datetime(bv["session_date"]).dt.date

    print(f"\nLoaded {len(bv):,} bars across {bv['session_date'].nunique()} sessions")

    # Cross-check: 60s window should match Phase 2's per_bar_volumes
    print("\nSanity check vs Phase 2 (60s window):")
    p2 = pd.read_parquet(REPO / "diagnostics/mbp10-trcb-v1/per_bar_volumes.parquet")
    if not isinstance(p2["bar_close_utc"].dtype, pd.DatetimeTZDtype):
        p2["bar_close_utc"] = pd.to_datetime(p2["bar_close_utc"], utc=True)
    merged = bv.merge(p2[["bar_close_utc", "dir_buy_vol_60s", "dir_sell_vol_60s"]],
                      on="bar_close_utc", how="inner")
    diff_buy = (merged["buy_vol_60s"] != merged["dir_buy_vol_60s"]).sum()
    diff_sell = (merged["sell_vol_60s"] != merged["dir_sell_vol_60s"]).sum()
    print(f"  rows merged: {len(merged):,}    buy_vol diffs: {diff_buy}    sell_vol diffs: {diff_sell}")
    if diff_buy > 0 or diff_sell > 0:
        print("  WARNING: 60s vols don't match Phase 2; investigate before reporting.")

    # ES → 5min + ATR
    es_1s = pd.read_parquet(ES_1S_PATH, columns=["high", "low", "close"])
    if not isinstance(es_1s.index.dtype, pd.DatetimeTZDtype):
        es_1s.index = pd.to_datetime(es_1s.index, utc=True).tz_convert(TIMEZONE)
    es_5 = (es_1s.resample("5min", label="right", closed="right")
                  .agg({"high": "max", "low": "min", "close": "last"})
                  .dropna(subset=["close"]))
    tr = true_range(es_5["high"], es_5["low"], es_5["close"])
    atr_5 = wilder_atr(tr, ATR_WINDOW)
    close_5 = es_5["close"]
    es_1s_close = es_1s["close"]

    # Evaluate each window
    results = []
    for w in WINDOWS_S:
        print(f"\nEvaluating window {w}s…")
        stats = evaluate_window(bv, w, es_1s_close, atr_5, close_5)
        results.append(stats)
        print(f"  n_long={stats['n_long']}  n_short={stats['n_short']}  "
              f"trig_rate={stats['trig_rate_pct']:.4f}%  "
              f"mean_fwd={stats['mean_fwd_signed']:+.4f}  "
              f"t={stats['t_stat']:+.4f}  sep={stats['sep_vs_uncond']:+.4f}")

    # Comparison table
    print()
    print("=" * 78)
    print("WINDOW LENGTH SENSITIVITY — comparison table")
    print("=" * 78)
    print(f"  {'window':>7s}  {'n_long':>6s}  {'n_short':>7s}  {'n_trig':>6s}  "
          f"{'trig_rate':>10s}  {'mean_fwd':>9s}  {'t_stat':>7s}  {'sep_vs_uncond':>13s}  {'%pos':>5s}")
    for r in results:
        w_s = f"{r['window_s']}s"
        rate = f"{r['trig_rate_pct']:.4f}%"
        mean_str = f"{r['mean_fwd_signed']:+.4f}" if not np.isnan(r['mean_fwd_signed']) else "—"
        t_str = f"{r['t_stat']:+.4f}" if not np.isnan(r['t_stat']) else "—"
        sep_str = f"{r['sep_vs_uncond']:+.4f}" if not np.isnan(r['sep_vs_uncond']) else "—"
        pp = f"{r['pct_pos_trig']:.1f}%" if not np.isnan(r['pct_pos_trig']) else "—"
        print(f"  {w_s:>7s}  {r['n_long']:>6d}  {r['n_short']:>7d}  {r['n_trig']:>6d}  "
              f"{rate:>10s}  {mean_str:>9s}  {t_str:>7s}  {sep_str:>13s}  {pp:>5s}")

    # Markdown report
    md = []
    md.append("# TRCB-v1 Post-Mortem Q2 — Window length sensitivity\n")
    md.append(f"**Re-stream of MBP-10 with 4 window lengths.** Locked parameters identical "
              f"to TRCB-v1 except window length; 25-min forward return horizon held fixed.")
    md.append(f"\n**Data:** `analysis/trcb-postmortem/per_bar_volumes_multiwindow.parquet` "
              f"({len(bv):,} bars × {bv['session_date'].nunique()} sessions)")
    md.append(f"\n**60s sanity check** against Phase 2 `per_bar_volumes.parquet`: "
              f"buy_vol diffs = {diff_buy}, sell_vol diffs = {diff_sell} on {len(merged):,} merged rows.\n")
    md.append("## Comparison table\n")
    md.append("| window | n_long | n_short | n_trig | trig_rate | mean_fwd_25min (signed) | t vs 0 | sep vs uncond | % > 0 |")
    md.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for r in results:
        mean_str = f"{r['mean_fwd_signed']:+.4f}" if not np.isnan(r['mean_fwd_signed']) else "—"
        t_str = f"{r['t_stat']:+.4f}" if not np.isnan(r['t_stat']) else "—"
        sep_str = f"{r['sep_vs_uncond']:+.4f}" if not np.isnan(r['sep_vs_uncond']) else "—"
        pp = f"{r['pct_pos_trig']:.1f}%" if not np.isnan(r['pct_pos_trig']) else "—"
        md.append(f"| {r['window_s']}s | {r['n_long']} | {r['n_short']} | {r['n_trig']} | "
                  f"{r['trig_rate_pct']:.4f}% | {mean_str} | {t_str} | {sep_str} | {pp} |")
    md.append("")
    md.append("## Reading\n")
    # Pick the window with the best (positive, highest) separation
    best = max(results, key=lambda r: (r["sep_vs_uncond"] if not np.isnan(r["sep_vs_uncond"]) else -1e9))
    worst = min(results, key=lambda r: (r["sep_vs_uncond"] if not np.isnan(r["sep_vs_uncond"]) else 1e9))
    md.append(f"- Best window by separation-vs-unconditional: **{best['window_s']}s** "
              f"(sep = {best['sep_vs_uncond']:+.4f}, n_trig = {best['n_trig']}, "
              f"t = {best['t_stat']:+.4f})")
    md.append(f"- Worst window by separation-vs-unconditional: **{worst['window_s']}s** "
              f"(sep = {worst['sep_vs_uncond']:+.4f}, n_trig = {worst['n_trig']})")
    md.append(f"- 60s (locked TRCB-v1): sep = {results[1]['sep_vs_uncond']:+.4f}, "
              f"n_trig = {results[1]['n_trig']}\n")
    md.append("## Caveats\n")
    md.append("- Sample sizes (n_trig) per window are small (single-digit to mid-double-digit). "
              "t-stats with these n values are noisy and should not be treated as evidence "
              "of mechanism existence at a particular window.")
    md.append("- This is a 4-point sweep, not a continuous sensitivity curve.")
    md.append("- 25-min forward return horizon is fixed for cross-window comparability. "
              "Q3 varies the horizon separately on the locked-60s triggered bars.\n")
    md.append("## Disclaimer\n")
    md.append("Diagnostic only. TRCB-v1 FAIL verdict unaffected. No new filter authorized.\n")

    OUT_MD.write_text("\n".join(md))
    print(f"\nSaved: {OUT_MD}")


if __name__ == "__main__":
    main()
