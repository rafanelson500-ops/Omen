"""Step 1 — ATR-conditioned analysis on all 504 bugfixed trades.

Read-only. Replicates OMEN's ATR formula from features.py (SMA(14) on
TR with per-session reset) but does NOT import or modify features.py.

LOCKED:
  ATR window:           14 bars
  Baseline window:      60 prior 5-min bars (same-session, min 20)
  Split:                terciles on eligible trades
"""
from __future__ import annotations

import datetime as dt
from datetime import datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

DISCLOSURE = """\
This analysis is exploratory diagnostic work on a heavily consumed
corpus during an active forward test. It is NOT pre-registered.
Results CANNOT authorize any modification to locked OMEN config
or pre-reg.

The 504-trade all-bugfixes corpus has been examined many times
across multiple diagnostics. Project-wide false discovery rate is
high. Any positive finding here can only be honestly evaluated on
a future pre-registered forward window after OMEN-minus-SL verdict.
"""

REPO = Path("/Users/rafanelson/Omen")
ES_PRIMARY = REPO / "backend/data/market/ES_c_0_ohlcv1s_2025-09-08_2026-04-27.parquet"
IS_BUGFIX = REPO / "diagnostics/all-bugfixes-baseline/is_all_bugfixes.csv"
OOS_BUGFIX = REPO / "diagnostics/all-bugfixes-baseline/oos_all_bugfixes.csv"
OUT_DIR = REPO / "diagnostics/vol-regime"
OUT_MD = OUT_DIR / "01_atr_conditioning.md"

ET = ZoneInfo("America/New_York")
ATR_WINDOW = 14
ATR_MIN_PERIODS = 5
BASELINE_WINDOW = 60
BASELINE_MIN_PERIODS = 20
SL_CELL = "SHORT_long"


def _load_trades() -> pd.DataFrame:
    is_df = pd.read_csv(IS_BUGFIX); is_df["sample"] = "IS"
    oos_df = pd.read_csv(OOS_BUGFIX); oos_df["sample"] = "OOS"
    df = pd.concat([is_df, oos_df], ignore_index=True)
    df["entry_time_utc"] = pd.to_datetime(df["entry_time"], utc=True)
    df["entry_time_et"] = df["entry_time_utc"].dt.tz_convert(ET)
    df["entry_date"] = df["entry_time_et"].dt.date
    df["side_label"] = np.where(df["side"] == 1, "LONG", "SHORT")
    df["cell"] = df["side_label"] + "_" + df["gamma_regime"].astype(str)
    df = df.sort_values("entry_time_utc").reset_index(drop=True)
    return df


def _load_es_5min(start: dt.date, end: dt.date) -> pd.DataFrame:
    """Resample ES 1s to 5-min RTH bars (matches market.load convention)."""
    df = pd.read_parquet(ES_PRIMARY, columns=["open", "high", "low", "close"])
    df.index = pd.to_datetime(df.index, utc=True).tz_convert(ET)
    df = df.sort_index()
    start_ts = pd.Timestamp(start, tz=ET)
    end_ts = pd.Timestamp(end + dt.timedelta(days=1), tz=ET)
    df = df[(df.index >= start_ts) & (df.index < end_ts)]
    t = df.index.time
    df = df[(t >= time(9, 30)) & (t < time(16, 0))]
    df = (df.resample("5min", label="right", closed="right")
            .agg({"open": "first", "high": "max", "low": "min", "close": "last"})
            .dropna(subset=["close"]))
    t = df.index.time
    df = df[(t > time(9, 30)) & (t <= time(16, 0))]
    return df


def _compute_atr_and_baseline(es5: pd.DataFrame) -> pd.DataFrame:
    """Per-session ATR and 60-bar baseline. Mirrors bugfixed features.py."""
    out = es5.copy()
    out["session_date"] = out.index.date
    sess = pd.Series(out.index.date, index=out.index, name="_session")
    # Per-session prev close
    pc = out["close"].groupby(sess).shift(1)
    h, l = out["high"], out["low"]
    tr = pd.concat([(h - l), (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    out["tr"] = tr
    out["atr14"] = tr.groupby(sess).transform(
        lambda s: s.rolling(ATR_WINDOW, min_periods=ATR_MIN_PERIODS).mean()
    )
    # 60-bar SMA of ATR, per-session
    out["atr_baseline_60"] = out["atr14"].groupby(sess).transform(
        lambda s: s.rolling(BASELINE_WINDOW, min_periods=BASELINE_MIN_PERIODS).mean()
    )
    # Count of valid ATR bars within same session preceding this bar
    out["prior_atr_count"] = out["atr14"].notna().groupby(sess).cumsum()
    return out


def _attach_atr_to_trades(trades: pd.DataFrame, es: pd.DataFrame) -> pd.DataFrame:
    """For each trade, look up baseline ATR at the bar BEFORE entry_time."""
    out = trades.copy()
    # Bar labels in ES are right-closed: bar labeled 12:35 covers (12:30, 12:35].
    # entry_time is the SIGNAL bar close = 12:35 in the example. Baseline ATR
    # should be the rolling-60 mean of ATR over the 60 prior bars ENDING at
    # the bar BEFORE the signal bar (i.e., the bar at entry_time - 5 min).
    bar_width = pd.Timedelta(minutes=5)
    lookup_ts = (out["entry_time_et"] - bar_width)
    lookup_ts_idx = pd.DatetimeIndex(lookup_ts)
    # Use asof / reindex with method='ffill' against ES index
    es_aligned = es[["atr14", "atr_baseline_60", "prior_atr_count",
                      "session_date"]].copy()
    es_aligned = es_aligned[~es_aligned.index.duplicated(keep="last")]
    aligned = es_aligned.reindex(lookup_ts_idx, method="ffill",
                                  tolerance=pd.Timedelta("5min"))
    out["atr_entry_recomputed"] = aligned["atr14"].values
    out["atr_baseline_60"] = aligned["atr_baseline_60"].values
    out["prior_atr_count_at_entry"] = aligned["prior_atr_count"].values
    # Same-session check: the ES bar's session_date must equal the trade's
    # entry_date. If lookup landed on a prior session (e.g., early-morning
    # trade with no in-session prior bars), the baseline is invalid.
    aligned_dates = aligned["session_date"].values
    out["lookup_session_match"] = np.array(
        [d1 == d2 for d1, d2 in zip(aligned_dates, out["entry_date"].values)]
    )
    return out


def _mark_eligibility(trades: pd.DataFrame) -> pd.DataFrame:
    out = trades.copy()
    # Eligible iff:
    #   - lookup landed in same session
    #   - baseline ATR is finite (at least BASELINE_MIN_PERIODS=20 prior bars)
    finite_baseline = out["atr_baseline_60"].notna()
    enough_history = out["prior_atr_count_at_entry"].fillna(0) >= BASELINE_MIN_PERIODS
    out["atr_baseline_unavailable"] = ~(out["lookup_session_match"]
                                          & finite_baseline & enough_history)
    return out


def _compute_atr_ratio(trades: pd.DataFrame, use_recomputed: bool = False) -> pd.DataFrame:
    """atr_ratio = atr_at_entry / atr_baseline_60. Use the trade log's
    atr_at_entry by default (this is what OMEN actually used for stop/target
    sizing). use_recomputed=True swaps in our own ATR computation, which is
    a sanity check.
    """
    out = trades.copy()
    numer = (out["atr_entry_recomputed"] if use_recomputed
             else out["atr_at_entry"])
    out["atr_ratio"] = numer / out["atr_baseline_60"]
    return out


def _max_drawdown(net: pd.Series, t: pd.Series) -> float:
    if len(net) == 0:
        return 0.0
    order = t.argsort()
    eq = np.cumsum(net.values[order])
    return float((eq - np.maximum.accumulate(eq)).min())


def _sharpe(net: pd.Series, n_sessions: int) -> float | None:
    n = len(net)
    if n < 2 or n_sessions <= 0:
        return None
    tpd = n / n_sessions
    m = float(net.mean()); s = float(net.std(ddof=1))
    if s == 0:
        return None
    return ((m * tpd) / (s * np.sqrt(tpd))) * np.sqrt(252)


def _group_stats(df: pd.DataFrame, label: str) -> dict:
    n = len(df)
    if n == 0:
        return {"label": label, "n": 0}
    net = df["net_dollars"]
    wins = net[net > 0]
    losses = net[net <= 0]
    avg_win = float(wins.mean()) if len(wins) else 0.0
    avg_loss = float(losses.mean()) if len(losses) else 0.0
    gross_p = float(wins.sum()) if len(wins) else 0.0
    gross_l = abs(float(losses.sum())) if len(losses) else 0.0
    pf = gross_p / gross_l if gross_l > 0 else (float("inf") if gross_p > 0 else 0.0)
    n_sessions = df["entry_date"].nunique()
    return {
        "label": label,
        "n": n,
        "sum": float(net.sum()),
        "win_rate": float((net > 0).mean()),
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "profit_factor": pf,
        "sharpe": _sharpe(net, n_sessions),
        "max_dd": _max_drawdown(net, df["entry_time_utc"]),
        "n_sessions": int(n_sessions),
    }


def _fmt(v, fmt="+.2f"):
    if v is None or (isinstance(v, float) and (np.isnan(v) or np.isinf(v))):
        return "—"
    return f"{v:{fmt}}"


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(DISCLOSURE)
    print("=" * 78)
    print("STEP 1 — ATR-conditioned analysis (504 trades)")
    print("=" * 78)

    trades = _load_trades()
    print(f"\nLoaded trades: {len(trades)}  "
          f"(IS={int((trades['sample']=='IS').sum())}, "
          f"OOS={int((trades['sample']=='OOS').sum())})")
    print(f"Date range: {trades['entry_date'].min()} → {trades['entry_date'].max()}")
    print(f"Sessions   : {trades['entry_date'].nunique()}")

    corpus_start = min(trades["entry_date"])
    corpus_end = max(trades["entry_date"])
    print(f"\nLoading ES 5-min bars [{corpus_start} → {corpus_end}] ...")
    es5 = _load_es_5min(corpus_start, corpus_end)
    print(f"  ES 5-min bars: {len(es5):,}  "
          f"({es5.index.min()} → {es5.index.max()})")

    es5 = _compute_atr_and_baseline(es5)
    n_atr_finite = int(es5["atr14"].notna().sum())
    n_baseline_finite = int(es5["atr_baseline_60"].notna().sum())
    print(f"  bars with finite atr14         : {n_atr_finite:,}")
    print(f"  bars with finite atr_baseline_60: {n_baseline_finite:,}")

    trades = _attach_atr_to_trades(trades, es5)
    trades = _mark_eligibility(trades)
    n_excluded = int(trades["atr_baseline_unavailable"].sum())
    n_eligible = len(trades) - n_excluded
    print(f"\nEligibility:")
    print(f"  eligible      : {n_eligible}")
    print(f"  excluded      : {n_excluded}")
    if n_excluded:
        ex = trades[trades["atr_baseline_unavailable"]].copy()
        ex_no_session_match = int((~ex["lookup_session_match"]).sum())
        ex_no_history = int((ex["lookup_session_match"]
                             & (ex["prior_atr_count_at_entry"].fillna(0)
                                < BASELINE_MIN_PERIODS)).sum())
        ex_no_baseline = int((ex["lookup_session_match"]
                              & ex["atr_baseline_60"].isna()).sum())
        print(f"    by reason:")
        print(f"      no same-session prior bar : {ex_no_session_match}")
        print(f"      < 20 prior bars in session: {ex_no_history}")
        print(f"      baseline NaN despite match: {ex_no_baseline}")

    trades = _compute_atr_ratio(trades, use_recomputed=False)
    # Sanity: compare our recomputed ATR to logged atr_at_entry
    eligible = trades[~trades["atr_baseline_unavailable"]].copy()
    sanity = (eligible["atr_entry_recomputed"] - eligible["atr_at_entry"]).abs()
    print(f"\nSanity (recomputed ATR vs logged atr_at_entry, on eligible trades):")
    print(f"  median absolute diff: {sanity.median():.6f}  "
          f"95th pct: {sanity.quantile(0.95):.6f}  max: {sanity.max():.6f}")

    # atr_ratio distribution
    ar = eligible["atr_ratio"].dropna()
    print(f"\natr_ratio distribution (n={len(ar)}):")
    print(f"  min={ar.min():.4f}  p25={ar.quantile(0.25):.4f}  "
          f"median={ar.median():.4f}  p75={ar.quantile(0.75):.4f}  "
          f"max={ar.max():.4f}")

    # Terciles on eligible
    low_b = float(ar.quantile(1/3))
    high_b = float(ar.quantile(2/3))
    print(f"\nTercile boundaries (LOCKED on eligible):")
    print(f"  low_ratio_boundary  (33rd pct): {low_b:.6f}")
    print(f"  high_ratio_boundary (67th pct): {high_b:.6f}")

    eligible["atr_regime"] = pd.cut(
        eligible["atr_ratio"], bins=[-np.inf, low_b, high_b, np.inf],
        labels=["Low-ATR", "Mid-ATR", "High-ATR"]
    ).astype(str)

    # Groups
    groups = {
        "A: All 504 trades (incl. excluded)": trades,
        "B: Low-ATR regime (eligible)": eligible[eligible["atr_regime"] == "Low-ATR"],
        "C: Mid-ATR regime (eligible)": eligible[eligible["atr_regime"] == "Mid-ATR"],
        "D: High-ATR regime (eligible)": eligible[eligible["atr_regime"] == "High-ATR"],
        "E: minus-SL ∩ Low-ATR": eligible[(eligible["atr_regime"] == "Low-ATR")
                                            & (eligible["cell"] != SL_CELL)],
        "F: minus-SL ∩ High-ATR": eligible[(eligible["atr_regime"] == "High-ATR")
                                             & (eligible["cell"] != SL_CELL)],
    }
    stats = [_group_stats(g, lbl) for lbl, g in groups.items()]

    # Print table
    print()
    print("=" * 78)
    print("ATR REGIME COMPARISON")
    print("=" * 78)
    print(f"  {'group':<38s}  {'N':>4s}  {'sum $':>10s}  {'win':>7s}  "
          f"{'avg win':>9s}  {'avg loss':>9s}  {'PF':>6s}  {'Sharpe':>7s}  "
          f"{'max DD':>10s}")
    for s in stats:
        if s["n"] == 0:
            print(f"  {s['label']:<38s}  empty"); continue
        print(f"  {s['label']:<38s}  {s['n']:>4d}  ${s['sum']:>+9.0f}  "
              f"{s['win_rate']*100:>6.1f}%  "
              f"${s['avg_win']:>+8.2f}  ${s['avg_loss']:>+8.2f}  "
              f"{s['profit_factor']:>5.2f}  {_fmt(s['sharpe']):>7s}  "
              f"${s['max_dd']:>+9.0f}")

    # Markdown
    L: list[str] = []
    L.append("# Step 1 — ATR-conditioned analysis (504 trades)\n")
    L.append("Branch: `analysis/vol-regime-conditioning-throwaway` (throwaway).")
    L.append(f"Generated: {datetime.now().isoformat(timespec='seconds')}\n")
    L.append("## Disclosure\n")
    L.append("```")
    L.append(DISCLOSURE)
    L.append("```\n")

    L.append("## Setup\n")
    L.append(f"- Trade pool: **{len(trades)} trades** "
             f"(IS={int((trades['sample']=='IS').sum())}, "
             f"OOS={int((trades['sample']=='OOS').sum())}), "
             f"**{trades['entry_date'].nunique()} sessions**, "
             f"{trades['entry_date'].min()} → {trades['entry_date'].max()}.")
    L.append(f"- ATR formula: `tr.rolling({ATR_WINDOW}, "
             f"min_periods={ATR_MIN_PERIODS}).mean()` per session — replicated "
             "from `features.py` (read-only).")
    L.append(f"- Baseline: `atr14.rolling({BASELINE_WINDOW}, "
             f"min_periods={BASELINE_MIN_PERIODS}).mean()` per session.")
    L.append("- Baseline lookup at bar **immediately preceding entry** "
             "(entry_time − 5 min), same-session only.")
    L.append("")

    L.append("## Eligibility\n")
    L.append(f"- Eligible : **{n_eligible}**")
    L.append(f"- Excluded : **{n_excluded}**")
    if n_excluded:
        ex = trades[trades["atr_baseline_unavailable"]].copy()
        ex_no_session_match = int((~ex["lookup_session_match"]).sum())
        ex_no_history = int((ex["lookup_session_match"]
                             & (ex["prior_atr_count_at_entry"].fillna(0)
                                < BASELINE_MIN_PERIODS)).sum())
        L.append(f"  - no same-session prior bar : {ex_no_session_match}")
        L.append(f"  - < 20 prior bars in session: {ex_no_history}")
    L.append("")

    L.append("## ATR sanity (recomputed vs logged `atr_at_entry`)\n")
    L.append(f"- median |Δ| = {sanity.median():.6f}")
    L.append(f"- 95th pct  = {sanity.quantile(0.95):.6f}")
    L.append(f"- max       = {sanity.max():.6f}")
    L.append("")
    L.append("(`atr_ratio` numerator uses the trade log's logged `atr_at_entry`, "
             "i.e. the value OMEN actually sized exits with.)")
    L.append("")

    L.append("## `atr_ratio` distribution (eligible trades)\n")
    L.append(f"- n           : {len(ar)}")
    L.append(f"- min         : {ar.min():.4f}")
    L.append(f"- p25         : {ar.quantile(0.25):.4f}")
    L.append(f"- median      : {ar.median():.4f}")
    L.append(f"- p75         : {ar.quantile(0.75):.4f}")
    L.append(f"- max         : {ar.max():.4f}")
    L.append("")
    L.append("## Tercile boundaries (LOCKED for future pre-reg)\n")
    L.append(f"- `low_ratio_boundary`  (33rd pct of eligible) = "
             f"**{low_b:.6f}**")
    L.append(f"- `high_ratio_boundary` (67th pct of eligible) = "
             f"**{high_b:.6f}**")
    L.append("")
    L.append("## Group metrics\n")
    L.append("| group | N | sum $ | win | avg win | avg loss | PF | Sharpe (ann.) | max DD |")
    L.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for s in stats:
        if s["n"] == 0:
            L.append(f"| {s['label']} | 0 | — | — | — | — | — | — | — |")
            continue
        L.append(f"| {s['label']} | {s['n']} | "
                 f"${s['sum']:+.0f} | "
                 f"{s['win_rate']*100:.1f}% | "
                 f"${s['avg_win']:+.2f} | "
                 f"${s['avg_loss']:+.2f} | "
                 f"{s['profit_factor']:.2f} | "
                 f"{_fmt(s['sharpe'])} | "
                 f"${s['max_dd']:+.0f} |")
    L.append("")

    OUT_MD.write_text("\n".join(L) + "\n")
    print(f"\nSaved: {OUT_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
