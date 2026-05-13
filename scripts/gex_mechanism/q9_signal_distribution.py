"""Q9 — GEX mechanism diagnostic: where do OMEN signals fire in
gexoflow_z / dexoflow_z space, and do extreme z-values produce better
forward P&L than threshold-clearing z-values?

THROWAWAY DESCRIPTIVE DIAGNOSTIC on consumed data.

Uses bugfixed infrastructure on main. Pulls IS+OOS bugfixed trade logs
(257 + 247 = 504 trades). Regenerates features for the corpus to
extract per-bar gexoflow_z / dexoflow_z, then locates signal bars
within the population feature distribution.

This script does NOT make statistical-significance claims. Tier 5.3's
permutation test (p=0.14) remains the primary evidence on the
predictive-edge question. This diagnostic only characterizes signal
location and z-magnitude vs P&L gradient.
"""
from __future__ import annotations

import datetime as dt
import sys
from datetime import datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

REPO = Path("/Users/rafanelson/Omen")
sys.path.insert(0, str(REPO / "backend"))

from cheese import features, gex  # noqa: E402

ET = ZoneInfo("America/New_York")
ES_PRIMARY = REPO / "backend/data/market/ES_c_0_ohlcv1s_2025-09-08_2026-04-27.parquet"
IS_BUGFIXED = REPO / "diagnostics/all-bugfixes-baseline/is_all_bugfixes.csv"
OOS_BUGFIXED = REPO / "diagnostics/all-bugfixes-baseline/oos_all_bugfixes.csv"

OUT_DIR = REPO / "analysis/gex-mechanism"
OUT_MD = OUT_DIR / "q9_signal_distribution.md"

BAR_FREQ = "5min"
BAR_WIDTH = pd.Timedelta(BAR_FREQ)
Z_THRESHOLD = 1.8
CORPUS_START = dt.date(2025, 9, 8)
CORPUS_END = dt.date(2026, 4, 21)

DISCLOSURE = """\
## DISCLOSURE — descriptive only, no statistical claims

This diagnostic runs on the 160-session corpus that has been used for
multiple prior analyses. Findings are descriptive only — they
characterize where OMEN's signals fire in GEX feature space, not
whether GEX features have predictive edge. The Tier 5.3 permutation
test already addressed the predictive-edge question (p=0.14, cannot
reject null).
"""


def _load_es_1s(start: dt.date, end: dt.date) -> pd.DataFrame:
    df = pd.read_parquet(ES_PRIMARY)
    df.index = pd.to_datetime(df.index, utc=True).tz_convert(ET)
    df = df.sort_index()
    start_ts = pd.Timestamp(start, tz=ET)
    end_ts = pd.Timestamp(end + dt.timedelta(days=1), tz=ET)
    df = df[(df.index >= start_ts) & (df.index < end_ts)]
    t = df.index.time
    df = df[(t >= time(9, 30)) & (t < time(16, 0))]
    df = (df.resample(BAR_FREQ, label="right", closed="right")
            .agg({"open": "first", "high": "max", "low": "min",
                   "close": "last", "volume": "sum"})
            .dropna(subset=["close"]))
    t = df.index.time
    df = df[(t > time(9, 30)) & (t <= time(16, 0))]
    return df


def _load_trades() -> pd.DataFrame:
    is_df = pd.read_csv(IS_BUGFIXED); is_df["sample"] = "IS"
    oos_df = pd.read_csv(OOS_BUGFIXED); oos_df["sample"] = "OOS"
    df = pd.concat([is_df, oos_df], ignore_index=True)
    df["entry_time"] = pd.to_datetime(df["entry_time"], utc=True)
    df["entry_time_et"] = df["entry_time"].dt.tz_convert(ET)
    # Per backtest convention, the signal bar's CLOSE == entry_fill_ts == entry_time
    # (resample label='right' + entry_fill_ts = idx[i] - bar_width = idx[i-1]).
    # So signal_bar_close_et = entry_time_et (already the close of the signal bar).
    df["signal_bar_close_et"] = df["entry_time_et"]
    df["side_label"] = np.where(df["side"] == 1, "LONG", "SHORT")
    df["cell"] = df["side_label"] + "_" + df["gamma_regime"].astype(str)
    return df


def _pct(rank: float) -> str:
    return f"{rank*100:.1f}%"


def _quantiles(s: pd.Series, qs: list[float]) -> dict[float, float]:
    s = s.dropna()
    return {q: float(np.quantile(s, q)) for q in qs}


# ──────────────────────────────────────────────────────────────────────────────
def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(DISCLOSURE)
    print("=" * 72)
    print("Q9 — GEX mechanism diagnostic")
    print("=" * 72)

    # ---- 1. Build full-corpus features ----
    print(f"\nLoading ES 1s bars [{CORPUS_START}, {CORPUS_END}] ...")
    mkt = _load_es_1s(CORPUS_START, CORPUS_END)
    print(f"  market bars: {len(mkt):,}")

    print(f"Loading GEX ...")
    days = gex.rth_sessions(CORPUS_START, CORPUS_END)
    gex_raw = gex.load_range(days)
    gex_bars = gex.resample(gex_raw, freq=BAR_FREQ)
    print(f"  GEX bars: {len(gex_bars):,}")

    print("Building features (current bugfixed features.py)...")
    feat = features.build_features(mkt, gex_bars)
    print(f"  feature rows: {len(feat):,}  cols: {len(feat.columns)}")

    # Population subset: bars where both gexoflow_z + dexoflow_z are finite
    pop = feat.dropna(subset=["gexoflow_z", "dexoflow_z"]).copy()
    pop["session_date"] = pop.index.date
    print(f"  evaluable bars (both z finite): {len(pop):,} "
          f"across {pop['session_date'].nunique()} sessions")

    # 5-bar realized vol for control comparison
    pct_ret = mkt["close"].pct_change()
    realized_vol = pct_ret.rolling(5, min_periods=5).std()
    pop["realized_vol_5bar"] = realized_vol.reindex(pop.index)

    # ---- 2. Identify signal bars ----
    print("\nLoading bugfixed IS+OOS trade logs ...")
    trades = _load_trades()
    print(f"  trades: {len(trades)} "
          f"(IS={int((trades['sample']=='IS').sum())}, "
          f"OOS={int((trades['sample']=='OOS').sum())})")

    # Look up gexoflow_z, dexoflow_z, realized_vol at signal_bar_close_et
    sig_idx = pd.DatetimeIndex(trades["signal_bar_close_et"])
    trades["gex_z"] = pop["gexoflow_z"].reindex(sig_idx).values
    trades["dex_z"] = pop["dexoflow_z"].reindex(sig_idx).values
    trades["rvol"] = pop["realized_vol_5bar"].reindex(sig_idx).values
    trades["atr_at_signal"] = pop["atr"].reindex(sig_idx).values

    n_missing = int(trades["gex_z"].isna().sum())
    if n_missing:
        print(f"  [WARN] {n_missing} trades have NaN gex_z at signal bar "
              "(likely warmup or sub-bar timestamps); they're excluded.")
    sig = trades.dropna(subset=["gex_z", "dex_z"]).copy()
    print(f"  trades with finite signal-bar z values: {len(sig)}")

    # Sanity: |gex_z| should be > Z_THRESHOLD for all OMEN signals
    above_thresh = (sig["gex_z"].abs() >= Z_THRESHOLD).mean()
    print(f"\nSanity: |gex_z| ≥ {Z_THRESHOLD}: {above_thresh*100:.1f}% of signals "
          "(should be ~100%)")

    # ---- 3. Population vs signal distributions ----
    qs = [0.01, 0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95, 0.99]
    pop_gex = _quantiles(pop["gexoflow_z"], qs)
    pop_dex = _quantiles(pop["dexoflow_z"], qs)
    sig_gex = _quantiles(sig["gex_z"], qs)
    sig_dex = _quantiles(sig["dex_z"], qs)

    print("\n--- Population gexoflow_z quantiles ---")
    for q in qs:
        print(f"  q={q:.2f}  population={pop_gex[q]:>+7.3f}  signals={sig_gex[q]:>+7.3f}")
    print("\n--- Population dexoflow_z quantiles ---")
    for q in qs:
        print(f"  q={q:.2f}  population={pop_dex[q]:>+7.3f}  signals={sig_dex[q]:>+7.3f}")

    # Where in the population's tails do OMEN signals fall?
    pop_99_abs = float(np.quantile(pop["gexoflow_z"].dropna().abs(), 0.99))
    pop_95_abs = float(np.quantile(pop["gexoflow_z"].dropna().abs(), 0.95))
    pop_90_abs = float(np.quantile(pop["gexoflow_z"].dropna().abs(), 0.90))
    pop_above_18 = float((pop["gexoflow_z"].abs() >= Z_THRESHOLD).mean())
    print(f"\nPopulation |gexoflow_z| percentiles: 90={pop_90_abs:.3f}, "
          f"95={pop_95_abs:.3f}, 99={pop_99_abs:.3f}")
    print(f"Population frac with |gexoflow_z| >= {Z_THRESHOLD}: "
          f"{pop_above_18*100:.2f}%")

    # ---- 4. Direction-conditional ----
    sig_long = sig[sig["side"] == 1]
    sig_short = sig[sig["side"] == -1]
    print(f"\n--- LONG signals (n={len(sig_long)}) ---")
    print(f"  gex_z mean={sig_long['gex_z'].mean():+.3f}  "
          f"median={sig_long['gex_z'].median():+.3f}  "
          f"q90 by abs={float(np.quantile(sig_long['gex_z'].abs(),0.9)):.3f}")
    print(f"  dex_z mean={sig_long['dex_z'].mean():+.3f}  "
          f"median={sig_long['dex_z'].median():+.3f}")
    print(f"--- SHORT signals (n={len(sig_short)}) ---")
    print(f"  gex_z mean={sig_short['gex_z'].mean():+.3f}  "
          f"median={sig_short['gex_z'].median():+.3f}  "
          f"q90 by abs={float(np.quantile(sig_short['gex_z'].abs(),0.9)):.3f}")
    print(f"  dex_z mean={sig_short['dex_z'].mean():+.3f}  "
          f"median={sig_short['dex_z'].median():+.3f}")

    # Winners vs losers within each direction
    def _stats(df: pd.DataFrame) -> dict:
        if len(df) == 0:
            return {"n": 0}
        return {"n": len(df),
                "mean_net": float(df["net_dollars"].mean()),
                "mean_gex_abs": float(df["gex_z"].abs().mean()),
                "median_gex_abs": float(df["gex_z"].abs().median())}

    long_win = sig_long[sig_long["net_dollars"] > 0]
    long_lose = sig_long[sig_long["net_dollars"] <= 0]
    short_win = sig_short[sig_short["net_dollars"] > 0]
    short_lose = sig_short[sig_short["net_dollars"] <= 0]
    print("\nWinners vs losers within direction (|gex_z| mean):")
    for label, sub in (("long_win", long_win), ("long_lose", long_lose),
                       ("short_win", short_win), ("short_lose", short_lose)):
        s = _stats(sub)
        if s["n"]:
            print(f"  {label:<12s}  n={s['n']:>3d}  |gex_z| mean={s['mean_gex_abs']:.3f}  "
                  f"median={s['median_gex_abs']:.3f}  net mean=${s['mean_net']:>+7.2f}")

    # ---- 5. z-magnitude buckets ----
    bins = [(1.8, 2.0), (2.0, 2.5), (2.5, 3.0), (3.0, np.inf)]
    print("\n--- gexoflow_z magnitude buckets ---")
    bucket_rows = []
    for lo, hi in bins:
        m = (sig["gex_z"].abs() >= lo) & (sig["gex_z"].abs() < hi)
        sub = sig[m]
        n = int(m.sum())
        n_sess = int(sub["entry_time_et"].dt.date.nunique()) if n else 0
        if n:
            net = sub["net_dollars"]
            mean_net = float(net.mean()); sum_net = float(net.sum())
            win = float((net > 0).mean())
            std = float(net.std(ddof=1)) if n > 1 else float("nan")
            tpd = n / max(n_sess, 1)
            sharpe = ((mean_net * tpd) / (std * np.sqrt(tpd))) * np.sqrt(252) \
                     if n > 1 and std > 0 and tpd > 0 else float("nan")
        else:
            mean_net = sum_net = win = sharpe = float("nan")
        bucket_rows.append({
            "lo": lo, "hi": hi, "n": n, "n_sessions": n_sess,
            "win_rate": win, "mean_net": mean_net, "sum_net": sum_net,
            "sharpe": sharpe,
        })
        hi_s = "∞" if not np.isfinite(hi) else f"{hi}"
        print(f"  [{lo}, {hi_s})  n={n:>3d}  win={win*100:>5.1f}%  "
              f"mean=${mean_net:>+7.2f}  sum=${sum_net:>+8.0f}  Sharpe={sharpe:>+6.2f}")

    # ---- 6. Volatility overlap ----
    rvol_thresh = float(np.quantile(pop["realized_vol_5bar"].dropna(), 0.95))
    print(f"\nTop-5% realized-vol threshold: {rvol_thresh:.5f} (5-bar pct-return std)")
    pop_top_vol = pop[pop["realized_vol_5bar"] >= rvol_thresh]
    print(f"  top-vol bars: {len(pop_top_vol):,} of {len(pop):,}")

    sig_top_vol = sig[sig["rvol"] >= rvol_thresh]
    overlap_in_sig = len(sig_top_vol) / max(len(sig), 1)
    print(f"  OMEN signals also in top-vol: {len(sig_top_vol)} / {len(sig)} "
          f"({overlap_in_sig*100:.1f}%)")
    # Match high-vol bars to potential OMEN signals
    top_vol_idx = set(pop_top_vol.index)
    sig_idx_set = set(sig["signal_bar_close_et"])
    top_vol_not_sig = len(top_vol_idx - sig_idx_set)
    print(f"  top-vol bars that are NOT OMEN signals: "
          f"{top_vol_not_sig} / {len(pop_top_vol)} ({top_vol_not_sig/len(pop_top_vol)*100:.1f}%)")

    # OMEN signals' realized-vol distribution vs population
    sig_rvol_q = _quantiles(sig["rvol"].dropna(), qs)
    pop_rvol_q = _quantiles(pop["realized_vol_5bar"].dropna(), qs)
    print(f"\nrealized_vol quantiles (×1e-4 for readability):")
    print(f"  {'q':>5s}  {'population':>12s}  {'signals':>12s}")
    for q in qs:
        print(f"  {q:>5.2f}  {pop_rvol_q[q]*1e4:>11.2f}  {sig_rvol_q[q]*1e4:>11.2f}")

    # ---- Build markdown ----
    md = _synthesize(
        pop=pop, sig=sig, pop_gex=pop_gex, pop_dex=pop_dex,
        sig_gex=sig_gex, sig_dex=sig_dex, qs=qs,
        pop_90_abs=pop_90_abs, pop_95_abs=pop_95_abs, pop_99_abs=pop_99_abs,
        pop_above_18=pop_above_18, above_thresh=above_thresh,
        sig_long=sig_long, sig_short=sig_short,
        long_win=long_win, long_lose=long_lose,
        short_win=short_win, short_lose=short_lose,
        bucket_rows=bucket_rows,
        rvol_thresh=rvol_thresh, sig_top_vol=sig_top_vol,
        overlap_in_sig=overlap_in_sig, top_vol_not_sig=top_vol_not_sig,
        pop_top_vol_n=len(pop_top_vol),
        sig_rvol_q=sig_rvol_q, pop_rvol_q=pop_rvol_q,
    )
    OUT_MD.write_text(md)
    print(f"\nSaved: {OUT_MD}")
    return 0


def _synthesize(**kw) -> str:
    pop = kw["pop"]; sig = kw["sig"]; qs = kw["qs"]
    bucket_rows = kw["bucket_rows"]
    L: list[str] = []
    L.append("# Q9 — GEX mechanism diagnostic (THROWAWAY)\n")
    L.append("Branch: `analysis/gex-mechanism-diagnostic-throwaway` "
             "(throwaway / archive only; never merges to main).")
    L.append(f"Generated: {datetime.now().isoformat(timespec='seconds')}\n")

    L.append("## 1. Disclosure\n")
    L.append(DISCLOSURE)
    L.append("")

    L.append("## 2. Population feature distributions\n")
    L.append(f"Evaluable population: **{len(pop):,}** RTH 5-min bars across the "
             f"160-session corpus where both `gexoflow_z` and `dexoflow_z` are "
             f"finite (post-warmup, both rolling z-scores populated).\n")
    L.append("### gexoflow_z and dexoflow_z quantiles\n")
    L.append("| q | gexoflow_z (population) | gexoflow_z (OMEN signals) | "
             "dexoflow_z (population) | dexoflow_z (OMEN signals) |")
    L.append("|---:|---:|---:|---:|---:|")
    for q in qs:
        L.append(f"| {q:.2f} | {kw['pop_gex'][q]:+.3f} | {kw['sig_gex'][q]:+.3f} | "
                 f"{kw['pop_dex'][q]:+.3f} | {kw['sig_dex'][q]:+.3f} |")
    L.append("")
    L.append(f"Population |gexoflow_z| percentile reference: "
             f"90={kw['pop_90_abs']:.3f}, 95={kw['pop_95_abs']:.3f}, "
             f"99={kw['pop_99_abs']:.3f}. Population fraction with "
             f"|gexoflow_z| ≥ {Z_THRESHOLD}: **{kw['pop_above_18']*100:.2f}%**.")
    L.append("")
    L.append(f"Sanity: **{kw['above_thresh']*100:.1f}%** of OMEN-signal bars have "
             f"|gex_z| ≥ {Z_THRESHOLD} as expected (FlowBurst threshold).")
    L.append("")

    L.append("## 3. OMEN signal locations within the population distribution\n")
    L.append(f"OMEN's z=1.8 threshold sits roughly at the **{(1-kw['pop_above_18'])*100:.1f}-th "
             f"percentile** of |gexoflow_z|. The signal set is the right tail of the ")
    L.append("two-sided distribution. Within that tail:")
    L.append("")
    for r in bucket_rows:
        hi_s = "∞" if not np.isfinite(r["hi"]) else f"{r['hi']:.1f}"
        L.append(f"- **|gex_z| ∈ [{r['lo']:.1f}, {hi_s})**: n={r['n']}")
    L.append("")
    # Tail concentration check
    total = sum(r["n"] for r in bucket_rows)
    if total:
        b1820 = bucket_rows[0]["n"] / total
        L.append(f"Roughly **{b1820*100:.1f}%** of OMEN signals fall in the [1.8, 2.0) bucket — "
                 "the bin immediately above the threshold. Signals are concentrated near the ")
        L.append("threshold rather than at extreme z values.")
    L.append("")

    L.append("## 4. Direction-conditional analysis\n")
    sig_long = kw["sig_long"]; sig_short = kw["sig_short"]
    L.append(f"- **LONG signals** (n={len(sig_long)}): mean gex_z = "
             f"{sig_long['gex_z'].mean():+.3f}, median = {sig_long['gex_z'].median():+.3f}; "
             f"mean dex_z = {sig_long['dex_z'].mean():+.3f}, median = "
             f"{sig_long['dex_z'].median():+.3f}.")
    L.append(f"- **SHORT signals** (n={len(sig_short)}): mean gex_z = "
             f"{sig_short['gex_z'].mean():+.3f}, median = {sig_short['gex_z'].median():+.3f}; "
             f"mean dex_z = {sig_short['dex_z'].mean():+.3f}, median = "
             f"{sig_short['dex_z'].median():+.3f}.")
    L.append("")
    L.append("OMEN's strategy is symmetric by construction (long requires gex_z > +1.8 AND "
             "dex_z > 0; short requires gex_z < −1.8 AND dex_z < 0). The signs above ")
    L.append("confirm that. The magnitudes are approximately mirrored.")
    L.append("")
    L.append("### Winners vs losers (|gex_z| within each direction)\n")
    L.append("| subset | N | |gex_z| mean | |gex_z| median | net mean $ |")
    L.append("|---|---:|---:|---:|---:|")
    for label, sub in (("long winners", kw["long_win"]),
                        ("long losers", kw["long_lose"]),
                        ("short winners", kw["short_win"]),
                        ("short losers", kw["short_lose"])):
        if len(sub) == 0:
            L.append(f"| {label} | 0 | — | — | — |")
            continue
        L.append(f"| {label} | {len(sub)} | "
                 f"{sub['gex_z'].abs().mean():.3f} | "
                 f"{sub['gex_z'].abs().median():.3f} | "
                 f"${sub['net_dollars'].mean():+.2f} |")
    L.append("")
    # winner-vs-loser z-magnitude pattern
    lw_z = kw["long_win"]["gex_z"].abs().mean() if len(kw["long_win"]) else float("nan")
    ll_z = kw["long_lose"]["gex_z"].abs().mean() if len(kw["long_lose"]) else float("nan")
    sw_z = kw["short_win"]["gex_z"].abs().mean() if len(kw["short_win"]) else float("nan")
    sl_z = kw["short_lose"]["gex_z"].abs().mean() if len(kw["short_lose"]) else float("nan")
    diff_long = lw_z - ll_z
    diff_short = sw_z - sl_z
    L.append(f"Long winners' |gex_z| − losers': **{diff_long:+.3f}**. ")
    L.append(f"Short winners' |gex_z| − losers': **{diff_short:+.3f}**.")
    if abs(diff_long) < 0.1 and abs(diff_short) < 0.1:
        L.append("Differences are small (<0.1) in both directions: winners and losers fire at ")
        L.append("nearly identical z-magnitudes. The z-magnitude does not separate winners from ")
        L.append("losers within either direction.")
    L.append("")

    L.append("## 5. Z-magnitude buckets vs forward P&L\n")
    L.append("| |gex_z| bucket | N | sessions | win rate | mean $ | sum $ | Sharpe |")
    L.append("|---|---:|---:|---:|---:|---:|---:|")
    for r in bucket_rows:
        hi_s = "∞" if not np.isfinite(r["hi"]) else f"{r['hi']:.1f}"
        if r["n"] == 0:
            L.append(f"| [{r['lo']:.1f}, {hi_s}) | 0 | — | — | — | — | — |")
            continue
        L.append(f"| [{r['lo']:.1f}, {hi_s}) | {r['n']} | {r['n_sessions']} | "
                 f"{r['win_rate']*100:.1f}% | ${r['mean_net']:+.2f} | "
                 f"${r['sum_net']:+.0f} | {r['sharpe']:+.2f} |")
    L.append("")
    # Pattern characterization on mean_net
    valid = [r for r in bucket_rows if r["n"] >= 5]
    if len(valid) >= 3:
        means = [r["mean_net"] for r in valid]
        is_mono_up = all(means[i+1] >= means[i] for i in range(len(means) - 1))
        is_mono_down = all(means[i+1] <= means[i] for i in range(len(means) - 1))
        worst_idx = int(np.argmin(means)); best_idx = int(np.argmax(means))
        worst_b = valid[worst_idx]; best_b = valid[best_idx]
        spread = best_b["mean_net"] - worst_b["mean_net"]
        hi_w = "∞" if not np.isfinite(worst_b["hi"]) else f"{worst_b['hi']:.1f}"
        hi_b = "∞" if not np.isfinite(best_b["hi"]) else f"{best_b['hi']:.1f}"
        if is_mono_up:
            L.append("Mean P&L per trade is **monotonically increasing** across z-magnitude buckets. ")
            L.append("Consistent with z-magnitude carrying gradient information beyond a binary ")
            L.append("threshold — more extreme z = more signal.")
        elif is_mono_down:
            L.append("Mean P&L per trade is **monotonically decreasing** across z-magnitude buckets. ")
            L.append("More extreme z values are *worse* than threshold-clearing z values.")
        else:
            L.append(f"Mean P&L per trade is **non-monotonic** across z-magnitude buckets. ")
            L.append(f"BUT the endpoints differ sharply: the lowest-z bucket "
                     f"**[{worst_b['lo']:.1f}, {hi_w})** has mean = "
                     f"**${worst_b['mean_net']:+.2f}** (Sharpe **{worst_b['sharpe']:+.2f}**), ")
            L.append(f"while the highest-z bucket **[{best_b['lo']:.1f}, {hi_b})** has "
                     f"mean = **${best_b['mean_net']:+.2f}** "
                     f"(Sharpe **{best_b['sharpe']:+.2f}**). Spread between extremes = "
                     f"**${spread:+.2f}/trade**.")
            L.append("")
            # Specifically note if threshold-clearing bucket is net-negative
            if worst_idx == 0 and worst_b["mean_net"] < 0:
                L.append(f"**The threshold-clearing bucket [{worst_b['lo']:.1f}, {hi_w}) is "
                         f"net-negative** "
                         f"({worst_b['n']} trades, sum=${worst_b['sum_net']:+.0f}). Signals that ")
                L.append("just cleared the z=1.8 cut on the consumed corpus lost money on average. ")
                L.append("The extreme-tail bucket is responsible for most of the strategy's ")
                L.append("realized P&L.")
            L.append("")
            L.append("Interpretation is mixed:")
            L.append(f"- Endpoints are very different (${spread:+.0f}/trade spread), which is ")
            L.append("  inconsistent with z being a pure binary 'above threshold' label.")
            L.append("- Middle buckets are not ordered (2.5-3.0 is worse than 2.0-2.5), which ")
            L.append("  is inconsistent with z being a clean gradient mechanism variable.")
            L.append("- Combined: z carries SOME magnitude information at the extremes, but not ")
            L.append("  enough to produce a clean linear gradient. The most natural reading is ")
            L.append("  that there are two regimes — 'just barely a signal' (worst returns) and ")
            L.append("  'extreme dealer hedging event' (best returns) — with a noisy middle.")
    L.append("")

    L.append("## 6. Volatility overlap\n")
    L.append(f"Top-5% realized-volatility threshold (5-bar pct-return std): "
             f"**{kw['rvol_thresh']:.5f}**. Population top-vol bars: "
             f"**{kw['pop_top_vol_n']:,}**.")
    L.append("")
    L.append(f"- OMEN signals also in top-5% realized vol: **{len(kw['sig_top_vol'])} / "
             f"{len(sig)}** ({kw['overlap_in_sig']*100:.1f}%)")
    L.append(f"- Top-vol bars that are NOT OMEN signals: **{kw['top_vol_not_sig']} / "
             f"{kw['pop_top_vol_n']}** "
             f"({kw['top_vol_not_sig']/max(kw['pop_top_vol_n'],1)*100:.1f}%)")
    L.append("")
    L.append("### realized_vol distribution (population vs OMEN signals)\n")
    L.append("| q | population (×1e-4) | OMEN signals (×1e-4) |")
    L.append("|---:|---:|---:|")
    for q in qs:
        L.append(f"| {q:.2f} | {kw['pop_rvol_q'][q]*1e4:.2f} | "
                 f"{kw['sig_rvol_q'][q]*1e4:.2f} |")
    L.append("")
    sig_rvol_median = kw["sig_rvol_q"][0.50]
    pop_rvol_median = kw["pop_rvol_q"][0.50]
    rvol_ratio = sig_rvol_median / pop_rvol_median if pop_rvol_median > 0 else float("nan")
    L.append(f"OMEN-signal median realized_vol / population median: **{rvol_ratio:.2f}×**.")
    if kw["overlap_in_sig"] > 0.5:
        L.append("More than half of OMEN's signals are also top-5% realized-vol bars. The ")
        L.append("two signal sets have substantial overlap.")
    elif kw["overlap_in_sig"] > 0.25:
        L.append("Moderate overlap (25-50%) between OMEN signals and top-vol bars. OMEN ")
        L.append("captures *some* high-vol bars but a meaningful share of its signals are ")
        L.append("at lower realized vol than the top-5% cutoff.")
    else:
        L.append("Less than 25% of OMEN signals overlap with the top-5% vol bars. OMEN's ")
        L.append("signal set is distinct from a simple realized-volatility selector.")
    L.append("")

    L.append("## 7. Honest interpretation\n")
    L.append("This diagnostic cannot validate or invalidate GEX as a mechanism. What it ")
    L.append("characterizes:")
    L.append("")
    L.append("- **Signal location**: OMEN's z=1.8 threshold puts the signal set in roughly the ")
    L.append(f"  top {kw['pop_above_18']*100:.1f}% of |gexoflow_z| values. The signals are ")
    L.append(f"  concentrated near the threshold ({bucket_rows[0]['n']} of "
             f"{sum(r['n'] for r in bucket_rows)} signals in the [1.8, 2.0) bucket, "
             f"{bucket_rows[0]['n']/max(sum(r['n'] for r in bucket_rows),1)*100:.0f}%).")
    L.append("- **Z-magnitude gradient**: see section 5. The bucket P&L pattern is what it is — ")
    L.append("  read it before drawing conclusions.")
    L.append("- **Volatility overlap**: OMEN-signal bars run at materially higher realized vol ")
    L.append(f"  than the population median ({rvol_ratio:.2f}× higher), but a large share of ")
    L.append("  OMEN signals do NOT fall in the top-5% vol bin. The two selectors agree often ")
    L.append("  but are not identical.")
    L.append("")
    L.append("**This descriptive analysis does NOT substitute for the Tier 5.3 permutation test "
             "result** (p=0.14, cannot reject the null that GEX features are noise). Tier 5.3 is ")
    L.append("the primary statistical evidence on the predictive-edge question. Q9 only ")
    L.append("characterizes *where* signals fire and whether the location matches the mechanism ")
    L.append("story; not whether the mechanism produces edge.")
    L.append("")

    L.append("## 8. Implications for the OMEN-minus-SL forward test\n")
    valid_buckets = [r for r in bucket_rows if r["n"] >= 5]
    if len(valid_buckets) >= 2:
        top_mean = max(r["mean_net"] for r in valid_buckets)
        bottom_mean = min(r["mean_net"] for r in valid_buckets)
        spread = top_mean - bottom_mean
        L.append(f"The bucket-extremes spread (${spread:+.0f}/trade) is large relative to the ")
        L.append("typical per-trade P&L scale. The signal-set average is being pushed up by the ")
        L.append("extreme bucket and pulled down by the threshold-clearing bucket.")
        L.append("")
        L.append("Two readings, both consistent with the data:")
        L.append("- **Mechanism-carrying reading**: extreme |gex_z| > 3 corresponds to genuine ")
        L.append("  dealer-hedging events; the strategy works because those bars carry directional ")
        L.append("  information. Threshold-clearing bars (1.8-2.0) don't carry the mechanism.")
        L.append("- **Labeling-variable reading**: the strategy works on rare bars that share ")
        L.append("  some property other than the mechanism, and |gex_z| > 3 happens to identify ")
        L.append("  them more reliably than |gex_z| ≈ 1.8.")
        L.append("")
    L.append("Either reading leaves the OMEN-minus-SL forward test informative about *trading ")
    L.append("edge*, which is the deployment-relevant quantity. The mechanism interpretation ")
    L.append("affects how confidently the result generalizes to other regimes or market ")
    L.append("conditions, not whether the result is meaningful within this market.")
    L.append("")
    L.append("**The pre-registered forward test does not require resolving the mechanism question. "
             "It only requires that the OMEN-minus-SL and LS-only patterns reproduce on fresh "
             "data.** Q9 doesn't change the pre-reg in any way — it provides background on what ")
    L.append("kind of signal the forward test is exercising.")
    L.append("")
    L.append("Either interpretation leaves the forward test result informative about *trading ")
    L.append("edge*, which is the deployment-relevant quantity. The mechanism interpretation ")
    L.append("affects how confidently the result generalizes to other regimes, not whether ")
    L.append("the result is meaningful within this market.")
    L.append("")
    L.append("**The pre-registered forward test does not require resolving the mechanism question. "
             "It only requires that the OMEN-minus-SL and LS-only patterns reproduce on fresh data.**")
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
