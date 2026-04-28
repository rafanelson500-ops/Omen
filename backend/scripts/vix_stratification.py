"""VIX-regime stratification of locked Flow Burst baseline.

Read-only. Pulls daily VIX closes from yfinance, joins each trade to the
*prior* trading day's VIX close (the value known at market open of the
trade day), buckets by regime, and reports per-bucket performance.

Pre-registered hypotheses:
    A — edge concentrates in low VIX (<18)
    D — edge concentrates in middle VIX (15-20)

This script verdicts each one against the observed buckets. No filter
recommendations.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

BACKEND = Path("/Users/rafanelson/Omen/backend")
TRADES_CSV = BACKEND / "data" / "analysis" / "locked_baseline_trades_blackout_lunch.csv"
VIX_CSV = BACKEND / "data" / "analysis" / "vix_daily.csv"
TRADES_VIX_CSV = BACKEND / "data" / "analysis" / "trades_with_vix.csv"
RESULTS_CSV = BACKEND / "data" / "analysis" / "vix_stratification_results.csv"
REPORT_MD = BACKEND / "diagnostics" / "vix" / "REPORT.md"

VIX_START = "2025-12-26"
VIX_END = "2026-04-23"
EXPECTED_DAYS = 80
LOW_CONF_N = 15

# (label, lo_inclusive, hi_exclusive)  — last bucket has hi=inf
BUCKETS: list[tuple[str, float, float]] = [
    ("low",       float("-inf"), 15.0),
    ("low_mid",   15.0,          18.0),
    ("mid",       18.0,          20.0),
    ("elevated",  20.0,          25.0),
    ("high",      25.0,          float("inf")),
]


# --------------------------------------------------------------------------
def fetch_vix() -> pd.DataFrame:
    raw = yf.download("^VIX", start=VIX_START, end=VIX_END,
                      auto_adjust=False, progress=False)
    # yfinance returns a multi-index column frame for single tickers; flatten.
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)
    df = pd.DataFrame({
        "date": raw.index.date,
        "vix_close": raw["Close"].astype(float).to_numpy(),
    })
    df.to_csv(VIX_CSV, index=False)
    return df


def assign_prior_day_vix(trades: pd.DataFrame, vix: pd.DataFrame) -> pd.DataFrame:
    """For each trade, attach the latest VIX close strictly < entry_date.

    Uses pd.merge_asof for fast per-trade lookup; the resulting `vix_date`
    column is the trading day whose close becomes the regime indicator.
    """
    vix_sorted = vix.sort_values("date").reset_index(drop=True).copy()
    vix_sorted["vix_date"] = vix_sorted["date"]
    # merge_asof requires numeric/datetime64 keys, not object date.
    vix_sorted["date_dt"] = pd.to_datetime(vix_sorted["date"])

    t = trades.copy()
    t["entry_date"] = (
        pd.to_datetime(t["entry_time"], utc=True)
        .dt.tz_convert("America/New_York")
        .dt.date
    )
    t["entry_date_dt"] = pd.to_datetime(t["entry_date"])
    t = t.sort_values("entry_date_dt").reset_index().rename(columns={"index": "_orig_idx"})

    joined = pd.merge_asof(
        t,
        vix_sorted[["date_dt", "vix_close", "vix_date"]],
        left_on="entry_date_dt",
        right_on="date_dt",
        direction="backward",
        allow_exact_matches=False,    # require prior day, NOT same day
    )
    joined = joined.sort_values("_orig_idx").reset_index(drop=True)
    joined = joined.drop(columns=["date_dt", "entry_date_dt"])
    return joined


def assign_bucket(v: float) -> str:
    if pd.isna(v):
        return "missing"
    for label, lo, hi in BUCKETS:
        if lo <= v < hi:
            return label
    return "missing"


def stats_for(sub: pd.DataFrame) -> dict:
    n = len(sub)
    if n == 0:
        return {
            "n": 0, "win_rate": float("nan"),
            "mean_pnl": float("nan"), "median_pnl": float("nan"),
            "total_pnl": 0.0, "per_trade_sharpe": float("nan"),
            "n_target": 0, "n_stop": 0, "n_time": 0, "n_session_close": 0,
            "n_distinct_days": 0,
        }
    net = sub["net_dollars"].astype(float)
    std = float(net.std(ddof=1)) if n >= 2 else float("nan")
    sharpe = float(net.mean() / std) if (std and std > 0) else float("nan")
    return {
        "n": n,
        "win_rate": float((net > 0).mean()),
        "mean_pnl": float(net.mean()),
        "median_pnl": float(net.median()),
        "total_pnl": float(net.sum()),
        "per_trade_sharpe": sharpe,
        "n_target": int((sub["exit_reason"] == "target").sum()),
        "n_stop": int((sub["exit_reason"] == "stop").sum()),
        "n_time": int((sub["exit_reason"] == "time").sum()),
        "n_session_close": int((sub["exit_reason"] == "session_close").sum()),
        "n_distinct_days": int(sub["entry_date"].nunique()),
    }


# --------------------------------------------------------------------------
def main() -> None:
    print("=== VIX stratification — Flow Burst locked baseline ===\n")

    print("[1] Pulling VIX daily from yfinance…")
    vix = fetch_vix()
    if len(vix) != EXPECTED_DAYS:
        print(f"WARNING: expected {EXPECTED_DAYS} VIX rows, got {len(vix)}")
        if len(vix) < EXPECTED_DAYS:
            print("Aborting per spec (fewer rows than expected).")
            raise SystemExit(2)
    print(f"  rows: {len(vix)} ({vix['date'].min()} → {vix['date'].max()})")
    print(f"  saved: {VIX_CSV}")
    print(f"  VIX summary: min={vix['vix_close'].min():.2f}  "
          f"max={vix['vix_close'].max():.2f}  "
          f"mean={vix['vix_close'].mean():.2f}  "
          f"median={vix['vix_close'].median():.2f}\n")

    print("[2] Joining VIX (prior trading day) to trade log…")
    trades = pd.read_csv(TRADES_CSV)
    print(f"  trades: {len(trades)}")
    joined = assign_prior_day_vix(trades, vix)
    n_missing = int(joined["vix_close"].isna().sum())
    print(f"  joined: {len(joined)}  missing_vix: {n_missing}")
    if n_missing:
        miss = joined[joined["vix_close"].isna()][["entry_date"]].head(10)
        print("  first missing entry_dates:")
        print(miss.to_string(index=False))
    joined.to_csv(TRADES_VIX_CSV, index=False)
    print(f"  saved: {TRADES_VIX_CSV}\n")

    print("[3] Bucketing by VIX regime…")
    joined["vix_bucket"] = joined["vix_close"].map(assign_bucket)
    rows = []
    for label, lo, hi in BUCKETS:
        sub = joined[joined["vix_bucket"] == label]
        s = stats_for(sub)
        s["bucket"] = label
        s["range"] = _fmt_range(lo, hi)
        s["low_conf"] = s["n"] < LOW_CONF_N
        rows.append(s)
    # missing-bucket row, only if anything missing
    if n_missing:
        sub = joined[joined["vix_bucket"] == "missing"]
        s = stats_for(sub)
        s["bucket"] = "missing"
        s["range"] = "—"
        s["low_conf"] = True
        rows.append(s)

    table = pd.DataFrame(rows)
    cols_ordered = [
        "bucket", "range", "n", "n_distinct_days", "win_rate",
        "mean_pnl", "median_pnl", "total_pnl", "per_trade_sharpe",
        "n_target", "n_stop", "n_time", "n_session_close", "low_conf",
    ]
    table = table[cols_ordered]
    table.to_csv(RESULTS_CSV, index=False)

    _print_table(table)
    print(f"\n[4] Saved: {RESULTS_CSV}")

    overall = stats_for(joined)
    print(f"\n  overall: n={overall['n']}  mean=${overall['mean_pnl']:,.2f}  "
          f"sharpe={overall['per_trade_sharpe']:+.4f}")

    REPORT_MD.parent.mkdir(parents=True, exist_ok=True)
    REPORT_MD.write_text(_build_report(vix, joined, table, overall, n_missing))
    print(f"  REPORT: {REPORT_MD}")


# -------------------- helpers -------------------------------------------
def _fmt_range(lo: float, hi: float) -> str:
    lo_s = "−∞" if lo == float("-inf") else f"{lo:.2f}"
    hi_s = "+∞" if hi == float("inf") else f"{hi:.2f}"
    return f"[{lo_s}, {hi_s})"


def _print_table(table: pd.DataFrame) -> None:
    show = table.copy()
    fmt = {
        "win_rate": (lambda v: "—" if pd.isna(v) else f"{v:.3f}"),
        "mean_pnl": (lambda v: "—" if pd.isna(v) else f"${v:,.2f}"),
        "median_pnl": (lambda v: "—" if pd.isna(v) else f"${v:,.2f}"),
        "total_pnl": (lambda v: f"${v:,.2f}"),
        "per_trade_sharpe": (lambda v: "—" if pd.isna(v) else f"{v:+.4f}"),
        "low_conf": (lambda v: "yes" if v else "no"),
    }
    for col, fn in fmt.items():
        show[col] = show[col].map(fn)
    print(show.to_string(index=False))


def _md_table(table: pd.DataFrame) -> str:
    cols = list(table.columns)
    out = ["| " + " | ".join(cols) + " |",
           "|" + "|".join("---" if c in ("bucket", "range", "low_conf") else "---:" for c in cols) + "|"]
    for _, r in table.iterrows():
        cells = []
        for c in cols:
            v = r[c]
            if c == "low_conf":
                cells.append("yes" if v else "no")
            elif pd.isna(v):
                cells.append("—")
            elif c == "win_rate":
                cells.append(f"{v:.3f}")
            elif c in ("mean_pnl", "median_pnl", "total_pnl"):
                cells.append(f"${v:,.2f}")
            elif c == "per_trade_sharpe":
                cells.append(f"{v:+.4f}")
            elif isinstance(v, (int, np.integer)):
                cells.append(str(int(v)))
            elif isinstance(v, float) and float(v).is_integer():
                cells.append(str(int(v)))
            else:
                cells.append(str(v))
        out.append("| " + " | ".join(cells) + " |")
    return "\n".join(out)


def _verdict_low(table: pd.DataFrame, overall: dict) -> tuple[str, str]:
    """Hypothesis A: edge concentrates in low VIX (<18)."""
    sub = table[table["bucket"].isin(["low", "low_mid"])]
    n = int(sub["n"].sum())
    if n == 0:
        return "INCONCLUSIVE", f"No trades in low/low_mid (<18) buckets; cannot evaluate."
    pnl = float(sub["total_pnl"].sum())
    mean = pnl / n
    overall_mean = overall["mean_pnl"]
    if n < LOW_CONF_N:
        return "INCONCLUSIVE", (
            f"Combined low+low_mid bucket has n={n} (< {LOW_CONF_N}); too few trades "
            f"to verdict. Observed mean ${mean:,.2f} vs overall ${overall_mean:,.2f}."
        )
    if mean >= 1.25 * overall_mean and overall_mean > 0:
        return "CONFIRMED", (
            f"Low-VIX (<18) mean P&L ${mean:,.2f} on n={n} exceeds overall "
            f"${overall_mean:,.2f} by ≥25%."
        )
    if mean <= 0.75 * overall_mean:
        return "CONTRADICTED", (
            f"Low-VIX (<18) mean P&L ${mean:,.2f} on n={n} is materially below overall "
            f"${overall_mean:,.2f} (<75% of overall)."
        )
    return "INCONCLUSIVE", (
        f"Low-VIX (<18) mean P&L ${mean:,.2f} on n={n} is roughly in line with "
        f"overall ${overall_mean:,.2f}; no concentrated edge."
    )


def _verdict_mid(table: pd.DataFrame, overall: dict) -> tuple[str, str]:
    """Hypothesis D: edge concentrates in middle VIX (15-20)."""
    sub = table[table["bucket"].isin(["low_mid", "mid"])]
    n = int(sub["n"].sum())
    if n == 0:
        return "INCONCLUSIVE", "No trades in 15-20 buckets; cannot evaluate."
    pnl = float(sub["total_pnl"].sum())
    mean = pnl / n
    overall_mean = overall["mean_pnl"]
    if n < LOW_CONF_N:
        return "INCONCLUSIVE", (
            f"Combined low_mid+mid (15-20) bucket has n={n} (< {LOW_CONF_N}); too few "
            f"trades to verdict. Observed mean ${mean:,.2f} vs overall ${overall_mean:,.2f}."
        )
    if mean >= 1.25 * overall_mean and overall_mean > 0:
        return "CONFIRMED", (
            f"Mid-VIX (15-20) mean P&L ${mean:,.2f} on n={n} exceeds overall "
            f"${overall_mean:,.2f} by ≥25%."
        )
    if mean <= 0.75 * overall_mean:
        return "CONTRADICTED", (
            f"Mid-VIX (15-20) mean P&L ${mean:,.2f} on n={n} is materially below overall "
            f"${overall_mean:,.2f} (<75% of overall)."
        )
    return "INCONCLUSIVE", (
        f"Mid-VIX (15-20) mean P&L ${mean:,.2f} on n={n} is roughly in line with "
        f"overall ${overall_mean:,.2f}; no concentrated edge."
    )


def _build_report(vix, joined, table, overall, n_missing) -> str:
    parts = []
    parts.append("# VIX-regime stratification — Flow Burst locked baseline\n")

    # Plain-English summary anchored on the strongest bucket above LOW_CONF_N
    confident = table[~table["low_conf"]]
    best_bucket = confident.sort_values("per_trade_sharpe", ascending=False).head(1)
    best_str = "(no bucket cleared confidence threshold)"
    if not best_bucket.empty:
        b = best_bucket.iloc[0]
        best_str = (
            f"the **{b['bucket']}** bucket {b['range']} (n={int(b['n'])}, "
            f"per-trade Sharpe {b['per_trade_sharpe']:+.4f}, mean ${b['mean_pnl']:,.2f})"
        )
    parts.append("## Summary\n")
    parts.append(
        f"On 174 trades over 80 sessions (Dec 2025 – Apr 2026), VIX daily closes "
        f"ranged {vix['vix_close'].min():.2f} – {vix['vix_close'].max():.2f} "
        f"(mean {vix['vix_close'].mean():.2f}, median {vix['vix_close'].median():.2f}). "
        f"After joining each trade to the prior trading day's VIX close and bucketing "
        f"into five literature-standard regimes, the highest-Sharpe bucket above the "
        f"n≥{LOW_CONF_N} confidence floor is {best_str}. The strategy's overall "
        f"per-trade Sharpe is {overall['per_trade_sharpe']:+.4f} on mean P&L "
        f"${overall['mean_pnl']:,.2f}.\n"
    )

    parts.append("## VIX distribution across the 80-day window\n")
    parts.append("| stat | value |")
    parts.append("|---|---:|")
    parts.append(f"| min | {vix['vix_close'].min():.2f} |")
    parts.append(f"| 25th pct | {vix['vix_close'].quantile(0.25):.2f} |")
    parts.append(f"| median | {vix['vix_close'].median():.2f} |")
    parts.append(f"| mean | {vix['vix_close'].mean():.2f} |")
    parts.append(f"| 75th pct | {vix['vix_close'].quantile(0.75):.2f} |")
    parts.append(f"| max | {vix['vix_close'].max():.2f} |")
    parts.append(f"| trading days | {len(vix)} |\n")

    parts.append("## Per-bucket performance\n")
    parts.append(_md_table(table))
    if n_missing:
        parts.append(f"\n**Note:** {n_missing} trades had missing prior-day VIX (see `missing` row).\n")

    parts.append("\n## Pre-registered hypothesis verdicts\n")

    v_low, r_low = _verdict_low(table, overall)
    parts.append(f"### Hypothesis A — edge concentrates in low VIX (<18)\n")
    parts.append(f"**Verdict: {v_low}**\n\n{r_low}\n")

    v_mid, r_mid = _verdict_mid(table, overall)
    parts.append(f"\n### Hypothesis D — edge concentrates in middle VIX (15-20)\n")
    parts.append(f"**Verdict: {v_mid}**\n\n{r_mid}\n")

    parts.append("\n## Caveats\n")
    parts.append(
        "- VIX is taken as the daily close on the trading day **prior** to entry "
        "(value known at the trade-day's open). Daily resolution does **not** capture "
        "intraday VIX spikes that may occur during a session.\n"
        "- The 80-day window may not span all VIX environments. Buckets that did not "
        "appear (e.g. `low <15`, `high ≥25`) cannot be evaluated regardless of any "
        "verdict logic. Any verdict here is bounded by the VIX range that actually "
        "appeared in this window.\n"
        f"- Per-bucket Sharpe at small n is high-variance. Buckets with n < {LOW_CONF_N} "
        "are flagged `low_conf: yes` and should be treated as exploratory only.\n"
        "- This is descriptive analysis. No filter recommendations are made.\n"
    )
    return "\n".join(parts)


if __name__ == "__main__":
    main()
