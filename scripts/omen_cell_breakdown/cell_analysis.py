"""OMEN side × gamma_regime cell breakdown — IS vs OOS analysis.

Exploratory diagnostic on consumed data. No deployment decisions follow
from this script. Findings only inform whether any cell-level subset
warrants future fresh-data testing.

Steps 1–7 per pre-reg (in-message): cell assignment, per-cell stats,
IS-vs-OOS comparison, significance tests with Bonferroni correction,
regime-distribution shift check, OMEN-minus-SL view, time-of-day per
positive-OOS-Sharpe cell.

Outputs:
  analysis/omen-cell-breakdown/cell_stats.csv
  analysis/omen-cell-breakdown/per_cell_tests.csv
  analysis/omen-cell-breakdown/cell_summary_terminal.txt   (verbose dump)
  analysis/omen-cell-breakdown/SYNTHESIS.md                (written separately)
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as sps

REPO = Path("/Users/rafanelson/Omen")
IS_PATH = REPO / "backend/data/analysis/locked_baseline_trades_blackout_lunch.csv"
OOS_PATH = REPO / "backend/data/analysis/oos_baseline_trades_2025-09-08_2025-12-23.csv"
OUT_DIR = REPO / "analysis/omen-cell-breakdown"

CELLS = ["LONG_long", "LONG_short", "SHORT_long", "SHORT_short"]
SAMPLES = ["IS", "OOS"]
N_BOOTSTRAP = 10_000
RNG_SEED = 42

HOUR_BUCKETS = [
    ("09:30-10:29", 9 * 60 + 30, 10 * 60 + 30),
    ("10:30-11:29", 10 * 60 + 30, 11 * 60 + 30),
    ("11:30-12:29", 11 * 60 + 30, 12 * 60 + 30),
    ("12:30-13:29", 12 * 60 + 30, 13 * 60 + 30),
    ("13:30-14:29", 13 * 60 + 30, 14 * 60 + 30),
    ("14:30-15:29", 14 * 60 + 30, 15 * 60 + 30),
    ("15:30-15:55", 15 * 60 + 30, 15 * 60 + 55 + 1),
]


# ---------- Loading + cell assignment ---------------------------------------
def load_trades() -> pd.DataFrame:
    is_df = pd.read_csv(IS_PATH)
    is_df["sample"] = "IS"
    oos_df = pd.read_csv(OOS_PATH)
    oos_df["sample"] = "OOS"
    if "hour_min" not in oos_df.columns:
        oos_df["hour_min"] = pd.NA
    df = pd.concat([is_df, oos_df], ignore_index=True)
    df["entry_time"] = pd.to_datetime(df["entry_time"], utc=True).dt.tz_convert("America/New_York")
    df["exit_time"] = pd.to_datetime(df["exit_time"], utc=True).dt.tz_convert("America/New_York")
    df["entry_date"] = df["entry_time"].dt.date
    df["side_label"] = np.where(df["side"] == 1, "LONG", "SHORT")
    df["cell"] = df["side_label"] + "_" + df["gamma_regime"].astype(str)
    df["minute_of_day"] = df["entry_time"].dt.hour * 60 + df["entry_time"].dt.minute
    return df


# ---------- Stats helpers ---------------------------------------------------
def max_drawdown(net_dollars: pd.Series, entry_time: pd.Series) -> float:
    """Cumulative-sum max drawdown ordered by entry_time."""
    order = entry_time.argsort()
    eq = np.cumsum(net_dollars.values[order])
    peak = np.maximum.accumulate(eq)
    dd = eq - peak
    return float(dd.min()) if len(dd) else 0.0


def cell_sharpe(net: pd.Series, n_sessions: int) -> float:
    """Per pre-reg formula: scale per-trade stats to daily, then annualize."""
    n = len(net)
    if n < 2 or n_sessions <= 0:
        return float("nan")
    tpd = n / n_sessions
    if tpd <= 0:
        return float("nan")
    mean_t = float(net.mean())
    std_t = float(net.std(ddof=1))
    if std_t == 0:
        return float("nan")
    daily_mean = mean_t * tpd
    daily_std = std_t * np.sqrt(tpd)
    return (daily_mean / daily_std) * np.sqrt(252)


def bootstrap_mean_ci(net: np.ndarray, n_iter: int = N_BOOTSTRAP,
                     seed: int = RNG_SEED) -> tuple[float, float, float]:
    if len(net) < 2:
        return (float("nan"), float("nan"), float("nan"))
    rng = np.random.default_rng(seed)
    means = np.empty(n_iter)
    for i in range(n_iter):
        s = rng.choice(net, size=len(net), replace=True)
        means[i] = s.mean()
    return (float(np.percentile(means, 2.5)),
            float(np.median(means)),
            float(np.percentile(means, 97.5)))


def bootstrap_sharpe_ci(net: np.ndarray, n_sessions: int,
                       n_iter: int = N_BOOTSTRAP,
                       seed: int = RNG_SEED) -> tuple[float, float, float]:
    if len(net) < 2 or n_sessions <= 0:
        return (float("nan"), float("nan"), float("nan"))
    rng = np.random.default_rng(seed + 7)
    sharpes = np.empty(n_iter)
    n = len(net)
    tpd = n / n_sessions
    for i in range(n_iter):
        s = rng.choice(net, size=n, replace=True)
        m = s.mean()
        sd = s.std(ddof=1)
        sharpes[i] = ((m * tpd) / (sd * np.sqrt(tpd))) * np.sqrt(252) if sd > 0 else np.nan
    sharpes = sharpes[~np.isnan(sharpes)]
    if len(sharpes) == 0:
        return (float("nan"), float("nan"), float("nan"))
    return (float(np.percentile(sharpes, 2.5)),
            float(np.median(sharpes)),
            float(np.percentile(sharpes, 97.5)))


# ---------- Per-bucket stats (Step 2) ---------------------------------------
def per_bucket_stats(trades: pd.DataFrame, cell: str, sample: str,
                    sessions_in_sample: int) -> dict:
    sub = trades[(trades["cell"] == cell) & (trades["sample"] == sample)]
    n = len(sub)
    if n == 0:
        return {
            "cell": cell, "sample": sample, "n": 0,
            "sessions_in_sample": sessions_in_sample,
            "win_rate": np.nan, "mean": 0.0, "median": 0.0, "std": 0.0,
            "sum": 0.0, "sharpe": np.nan, "max_dd": 0.0, "mean_atr": np.nan,
            "exit_stop": 0, "exit_target": 0, "exit_time": 0, "exit_sess": 0,
        }
    net = sub["net_dollars"]
    exit_counts = sub["exit_reason"].value_counts()
    return {
        "cell": cell, "sample": sample, "n": n,
        "sessions_in_sample": sessions_in_sample,
        "win_rate": float((net > 0).mean()),
        "mean": float(net.mean()),
        "median": float(net.median()),
        "std": float(net.std(ddof=1)) if n > 1 else 0.0,
        "sum": float(net.sum()),
        "sharpe": cell_sharpe(net, sessions_in_sample),
        "max_dd": max_drawdown(net, sub["entry_time"]),
        "mean_atr": float(sub["atr_at_entry"].mean()),
        "exit_stop": int(exit_counts.get("stop", 0)),
        "exit_target": int(exit_counts.get("target", 0)),
        "exit_time": int(exit_counts.get("time", 0)),
        "exit_sess": int(exit_counts.get("session_close", 0)),
    }


def exit_mix_str(row: dict) -> str:
    n = row["n"]
    if n == 0:
        return "—"
    s = row["exit_stop"] / n * 100
    t = row["exit_target"] / n * 100
    i = row["exit_time"] / n * 100
    c = row["exit_sess"] / n * 100
    return f"s{s:.0f}/t{t:.0f}/i{i:.0f}/c{c:.0f}"


# ---------- Significance tests (Step 4) -------------------------------------
def cell_tests(trades: pd.DataFrame, cell: str, n_cells: int = 4) -> dict:
    is_net = trades.loc[(trades["cell"] == cell) & (trades["sample"] == "IS"),
                        "net_dollars"].values
    oos_net = trades.loc[(trades["cell"] == cell) & (trades["sample"] == "OOS"),
                        "net_dollars"].values

    out = {"cell": cell, "n_is": len(is_net), "n_oos": len(oos_net)}

    if len(oos_net) >= 2:
        tt = sps.ttest_1samp(oos_net, popmean=0.0)
        out["oos_t_vs_zero"] = float(tt.statistic)
        out["oos_p_raw"] = float(tt.pvalue)
        out["oos_p_bonf"] = float(min(1.0, tt.pvalue * n_cells))
        lo, mid, hi = bootstrap_mean_ci(oos_net)
        out["oos_mean_ci_low"] = lo
        out["oos_mean_ci_mid"] = mid
        out["oos_mean_ci_high"] = hi
    else:
        for k in ("oos_t_vs_zero", "oos_p_raw", "oos_p_bonf",
                  "oos_mean_ci_low", "oos_mean_ci_mid", "oos_mean_ci_high"):
            out[k] = float("nan")

    if len(is_net) >= 2 and len(oos_net) >= 2:
        wt = sps.ttest_ind(is_net, oos_net, equal_var=False)
        out["welch_t_is_vs_oos"] = float(wt.statistic)
        out["welch_p_is_vs_oos"] = float(wt.pvalue)
    else:
        out["welch_t_is_vs_oos"] = float("nan")
        out["welch_p_is_vs_oos"] = float("nan")

    return out


# ---------- Regime + side distribution shift (Step 5) -----------------------
def distribution_shift_check(trades: pd.DataFrame) -> dict:
    out = {}
    # By trade: gamma_regime distribution
    is_trades = trades[trades["sample"] == "IS"]
    oos_trades = trades[trades["sample"] == "OOS"]
    out["is_regime_pct_long"] = float((is_trades["gamma_regime"] == "long").mean() * 100)
    out["is_regime_pct_short"] = float((is_trades["gamma_regime"] == "short").mean() * 100)
    out["oos_regime_pct_long"] = float((oos_trades["gamma_regime"] == "long").mean() * 100)
    out["oos_regime_pct_short"] = float((oos_trades["gamma_regime"] == "short").mean() * 100)
    contingency = np.array([
        [int((is_trades["gamma_regime"] == "long").sum()),
         int((is_trades["gamma_regime"] == "short").sum())],
        [int((oos_trades["gamma_regime"] == "long").sum()),
         int((oos_trades["gamma_regime"] == "short").sum())],
    ])
    chi2, p, dof, _ = sps.chi2_contingency(contingency)
    out["regime_chi2"] = float(chi2)
    out["regime_chi2_p"] = float(p)
    out["regime_contingency"] = contingency.tolist()

    # Side distribution
    out["is_side_pct_long"] = float((is_trades["side"] == 1).mean() * 100)
    out["is_side_pct_short"] = float((is_trades["side"] == -1).mean() * 100)
    out["oos_side_pct_long"] = float((oos_trades["side"] == 1).mean() * 100)
    out["oos_side_pct_short"] = float((oos_trades["side"] == -1).mean() * 100)
    side_cont = np.array([
        [int((is_trades["side"] == 1).sum()),
         int((is_trades["side"] == -1).sum())],
        [int((oos_trades["side"] == 1).sum()),
         int((oos_trades["side"] == -1).sum())],
    ])
    chi2s, ps, _, _ = sps.chi2_contingency(side_cont)
    out["side_chi2"] = float(chi2s)
    out["side_chi2_p"] = float(ps)
    out["side_contingency"] = side_cont.tolist()

    # By day: was the regime DISTRIBUTION different by trading day, not trade?
    # OMEN trades per day vary; "day-level" regime can be ambiguous if a day
    # has trades in both regimes. Use majority regime per day.
    def day_regime(df):
        rows = []
        for d, g in df.groupby("entry_date"):
            long_n = int((g["gamma_regime"] == "long").sum())
            short_n = int((g["gamma_regime"] == "short").sum())
            rows.append({"date": d, "regime": "long" if long_n > short_n else "short"})
        return pd.DataFrame(rows)

    is_days = day_regime(is_trades)
    oos_days = day_regime(oos_trades)
    out["is_day_pct_long"] = float((is_days["regime"] == "long").mean() * 100) if len(is_days) else float("nan")
    out["is_day_pct_short"] = float((is_days["regime"] == "short").mean() * 100) if len(is_days) else float("nan")
    out["oos_day_pct_long"] = float((oos_days["regime"] == "long").mean() * 100) if len(oos_days) else float("nan")
    out["oos_day_pct_short"] = float((oos_days["regime"] == "short").mean() * 100) if len(oos_days) else float("nan")
    return out


# ---------- OMEN-minus-SL (Step 6) ------------------------------------------
def omen_minus_sl_stats(trades: pd.DataFrame, sessions: dict) -> dict:
    """All cells except SHORT_long. Plus single-cell stats per sample."""
    out = {}
    for sample in SAMPLES:
        n_sess = sessions[sample]
        full = trades[trades["sample"] == sample]
        minus_sl = full[full["cell"] != "SHORT_long"]
        out[f"{sample}_full"] = {
            "n": len(full),
            "sum": float(full["net_dollars"].sum()),
            "mean": float(full["net_dollars"].mean()) if len(full) else float("nan"),
            "win_rate": float((full["net_dollars"] > 0).mean()) if len(full) else float("nan"),
            "sharpe": cell_sharpe(full["net_dollars"], n_sess),
            "max_dd": max_drawdown(full["net_dollars"], full["entry_time"]),
        }
        out[f"{sample}_minus_sl"] = {
            "n": len(minus_sl),
            "sum": float(minus_sl["net_dollars"].sum()),
            "mean": float(minus_sl["net_dollars"].mean()) if len(minus_sl) else float("nan"),
            "win_rate": float((minus_sl["net_dollars"] > 0).mean()) if len(minus_sl) else float("nan"),
            "sharpe": cell_sharpe(minus_sl["net_dollars"], n_sess),
            "max_dd": max_drawdown(minus_sl["net_dollars"], minus_sl["entry_time"]),
        }
        for cell in CELLS:
            sub = full[full["cell"] == cell]
            out[f"{sample}_only_{cell}"] = {
                "n": len(sub),
                "sum": float(sub["net_dollars"].sum()),
                "mean": float(sub["net_dollars"].mean()) if len(sub) else float("nan"),
                "win_rate": float((sub["net_dollars"] > 0).mean()) if len(sub) else float("nan"),
                "sharpe": cell_sharpe(sub["net_dollars"], n_sess),
                "max_dd": max_drawdown(sub["net_dollars"], sub["entry_time"]),
            }
    return out


# ---------- Time-of-day per cell (Step 7) -----------------------------------
def tod_per_cell(trades: pd.DataFrame, cell: str, sample: str) -> list[dict]:
    sub = trades[(trades["cell"] == cell) & (trades["sample"] == sample)]
    rows = []
    for label, lo, hi in HOUR_BUCKETS:
        mask = (sub["minute_of_day"] >= lo) & (sub["minute_of_day"] < hi)
        s = sub[mask]
        n = len(s)
        rows.append({
            "bucket": label, "n": n,
            "mean": float(s["net_dollars"].mean()) if n else float("nan"),
            "win_rate": float((s["net_dollars"] > 0).mean()) if n else float("nan"),
            "sum": float(s["net_dollars"].sum()),
        })
    return rows


# ---------- Main ------------------------------------------------------------
def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    buf = io.StringIO()

    def out(line: str = "") -> None:
        print(line)
        buf.write(line + "\n")

    trades = load_trades()
    out("=" * 78)
    out("OMEN SIDE × GAMMA_REGIME CELL BREAKDOWN")
    out("=" * 78)
    out(f"IS trades:  {(trades['sample'] == 'IS').sum()}")
    out(f"OOS trades: {(trades['sample'] == 'OOS').sum()}")
    out()

    # Session counts derived from trade log itself
    is_sessions = trades.loc[trades["sample"] == "IS", "entry_date"].nunique()
    oos_sessions = trades.loc[trades["sample"] == "OOS", "entry_date"].nunique()
    sessions = {"IS": is_sessions, "OOS": oos_sessions}
    out(f"IS sessions:  {is_sessions}")
    out(f"OOS sessions: {oos_sessions}")
    out()

    # ---- Step 2: per-bucket stats ----
    out("=" * 78)
    out("Step 2 — Per-bucket stats (4 cells × 2 samples)")
    out("=" * 78)
    rows = []
    for cell in CELLS:
        for sample in SAMPLES:
            r = per_bucket_stats(trades, cell, sample, sessions[sample])
            rows.append(r)
    stats_df = pd.DataFrame(rows)
    stats_df["exit_mix"] = stats_df.apply(lambda r: exit_mix_str(r), axis=1)
    stats_df.to_csv(OUT_DIR / "cell_stats.csv", index=False)

    # Print as a table
    out(f"{'cell':<12s} {'sample':<5s} {'n':>3s}  {'win':>6s} {'mean$':>9s} "
        f"{'std$':>9s} {'sum$':>10s} {'sharpe':>7s} {'maxDD$':>10s} {'meanATR':>8s} {'exit_mix':>15s}")
    for r in rows:
        wr = f"{r['win_rate']*100:.1f}%" if r["n"] else "—"
        out(f"{r['cell']:<12s} {r['sample']:<5s} {r['n']:>3d}  {wr:>6s} "
            f"{r['mean']:>+9.2f} {r['std']:>9.2f} {r['sum']:>+10.2f} "
            f"{r['sharpe']:>+7.3f} {r['max_dd']:>+10.2f} "
            f"{r['mean_atr']:>8.4f} {exit_mix_str(r):>15s}")
    out()

    # ---- Step 3: IS vs OOS per cell ----
    out("=" * 78)
    out("Step 3 — Per-cell IS vs OOS comparison")
    out("=" * 78)
    for cell in CELLS:
        is_r = next(r for r in rows if r["cell"] == cell and r["sample"] == "IS")
        oos_r = next(r for r in rows if r["cell"] == cell and r["sample"] == "OOS")
        out(f"\nCell: {cell}")
        out("─" * 78)
        out(f"  {'metric':<12s}  {'IS':>10s}  {'OOS':>10s}  {'delta':>11s}")
        out(f"  {'N':<12s}  {is_r['n']:>10d}  {oos_r['n']:>10d}  {oos_r['n']-is_r['n']:>+11d}")
        wr_i = is_r["win_rate"] * 100 if is_r["n"] else float("nan")
        wr_o = oos_r["win_rate"] * 100 if oos_r["n"] else float("nan")
        out(f"  {'win%':<12s}  {wr_i:>9.2f}%  {wr_o:>9.2f}%  {wr_o-wr_i:>+10.2f}pp")
        out(f"  {'mean$':<12s}  {is_r['mean']:>+10.2f}  {oos_r['mean']:>+10.2f}  "
            f"{oos_r['mean']-is_r['mean']:>+11.2f}")
        out(f"  {'sum$':<12s}  {is_r['sum']:>+10.2f}  {oos_r['sum']:>+10.2f}  "
            f"{oos_r['sum']-is_r['sum']:>+11.2f}")
        out(f"  {'sharpe':<12s}  {is_r['sharpe']:>+10.3f}  {oos_r['sharpe']:>+10.3f}  "
            f"{oos_r['sharpe']-is_r['sharpe']:>+11.3f}")
        out(f"  {'maxDD$':<12s}  {is_r['max_dd']:>+10.2f}  {oos_r['max_dd']:>+10.2f}  "
            f"{oos_r['max_dd']-is_r['max_dd']:>+11.2f}")
        out(f"  {'exit_mix':<12s}  {exit_mix_str(is_r):>10s}  {exit_mix_str(oos_r):>10s}")

    # ---- Step 4: Significance tests ----
    out()
    out("=" * 78)
    out("Step 4 — Statistical tests per cell (n_cells=4 for Bonferroni)")
    out("=" * 78)
    test_rows = []
    for cell in CELLS:
        t = cell_tests(trades, cell, n_cells=4)
        test_rows.append(t)
        out(f"\n{cell}:")
        out(f"  OOS n={t['n_oos']}")
        out(f"    t vs 0:           {t['oos_t_vs_zero']:+.4f}")
        out(f"    p (raw):          {t['oos_p_raw']:.5f}")
        out(f"    p (Bonferroni×4): {t['oos_p_bonf']:.5f}")
        out(f"    OOS mean 95% boot CI (10,000 resamples):")
        out(f"      [{t['oos_mean_ci_low']:+.2f}, {t['oos_mean_ci_high']:+.2f}], median {t['oos_mean_ci_mid']:+.2f}")
        out(f"  Welch IS vs OOS:")
        out(f"    t:                {t['welch_t_is_vs_oos']:+.4f}")
        out(f"    p:                {t['welch_p_is_vs_oos']:.5f}")
    pd.DataFrame(test_rows).to_csv(OUT_DIR / "per_cell_tests.csv", index=False)

    # ---- Step 5: regime + side distribution shift ----
    out()
    out("=" * 78)
    out("Step 5 — Regime + side distribution shift IS vs OOS")
    out("=" * 78)
    ds = distribution_shift_check(trades)
    out("\nGamma regime distribution (per-trade):")
    out(f"  IS:  long {ds['is_regime_pct_long']:.2f}%  /  short {ds['is_regime_pct_short']:.2f}%")
    out(f"  OOS: long {ds['oos_regime_pct_long']:.2f}%  /  short {ds['oos_regime_pct_short']:.2f}%")
    out(f"  Chi-square: {ds['regime_chi2']:.4f}  p={ds['regime_chi2_p']:.5f}")
    out(f"  Contingency [IS / OOS] x [long / short]: {ds['regime_contingency']}")
    out("\nGamma regime distribution (per-day majority):")
    out(f"  IS:  long {ds['is_day_pct_long']:.2f}%  /  short {ds['is_day_pct_short']:.2f}%")
    out(f"  OOS: long {ds['oos_day_pct_long']:.2f}%  /  short {ds['oos_day_pct_short']:.2f}%")
    out("\nSide distribution (per-trade):")
    out(f"  IS:  long {ds['is_side_pct_long']:.2f}%  /  short {ds['is_side_pct_short']:.2f}%")
    out(f"  OOS: long {ds['oos_side_pct_long']:.2f}%  /  short {ds['oos_side_pct_short']:.2f}%")
    out(f"  Chi-square: {ds['side_chi2']:.4f}  p={ds['side_chi2_p']:.5f}")

    # ---- Step 6: OMEN-minus-SL ----
    out()
    out("=" * 78)
    out("Step 6 — OMEN-minus-SL view + per-cell-only views")
    out("=" * 78)
    cuts = omen_minus_sl_stats(trades, sessions)
    out(f"\n{'view':<28s}  {'n':>4s}  {'mean$':>9s}  {'sum$':>10s}  {'win%':>6s}  "
        f"{'sharpe':>7s}  {'maxDD$':>10s}")
    out("─" * 78)
    for sample in SAMPLES:
        for key, label in [
            (f"{sample}_full", f"{sample} full (4 cells)"),
            (f"{sample}_minus_sl", f"{sample} minus SHORT_long"),
            (f"{sample}_only_LONG_long", f"{sample} only LONG_long"),
            (f"{sample}_only_LONG_short", f"{sample} only LONG_short"),
            (f"{sample}_only_SHORT_long", f"{sample} only SHORT_long"),
            (f"{sample}_only_SHORT_short", f"{sample} only SHORT_short"),
        ]:
            v = cuts[key]
            wr = f"{v['win_rate']*100:.1f}%" if v['n'] else "—"
            sharpe_s = f"{v['sharpe']:+.3f}" if not np.isnan(v['sharpe']) else "—"
            out(f"{label:<28s}  {v['n']:>4d}  {v['mean']:>+9.2f}  {v['sum']:>+10.2f}  "
                f"{wr:>6s}  {sharpe_s:>7s}  {v['max_dd']:>+10.2f}")
        if sample == "IS":
            out()

    # ---- Step 7: time-of-day for positive-OOS-Sharpe cells ----
    out()
    out("=" * 78)
    out("Step 7 — Time-of-day per OOS-positive-Sharpe cell (exploratory color)")
    out("=" * 78)
    positive_cells = [r["cell"] for r in rows
                      if r["sample"] == "OOS" and not np.isnan(r["sharpe"]) and r["sharpe"] > 0]
    if not positive_cells:
        out("  No cells with OOS Sharpe > 0.")
    for cell in positive_cells:
        out(f"\n{cell} — OOS (sharpe = "
            f"{next(r for r in rows if r['cell']==cell and r['sample']=='OOS')['sharpe']:+.3f}):")
        tod_rows = tod_per_cell(trades, cell, "OOS")
        out(f"  {'bucket':>12s}  {'n':>3s}  {'mean$':>9s}  {'win%':>6s}  {'sum$':>10s}")
        for r in tod_rows:
            wr = f"{r['win_rate']*100:.1f}%" if r['n'] else "—"
            mean_s = f"{r['mean']:+.2f}" if not np.isnan(r['mean']) else "—"
            out(f"  {r['bucket']:>12s}  {r['n']:>3d}  {mean_s:>9s}  {wr:>6s}  {r['sum']:>+10.2f}")

    # ---- Candidate flagging + bootstrap Sharpe CI ----
    out()
    out("=" * 78)
    out("Candidate flagging (OOS Sharpe > 1.5 AND N ≥ 30 AND Bonferroni p < 0.05)")
    out("=" * 78)
    candidates_data = []
    for cell in CELLS:
        r = next(rr for rr in rows if rr["cell"] == cell and rr["sample"] == "OOS")
        t = next(tt for tt in test_rows if tt["cell"] == cell)
        sharpe_ok = (not np.isnan(r["sharpe"])) and r["sharpe"] > 1.5
        n_ok = r["n"] >= 30
        p_ok = (not np.isnan(t["oos_p_bonf"])) and t["oos_p_bonf"] < 0.05
        flagged = sharpe_ok and n_ok and p_ok
        out(f"\n{cell}:")
        out(f"  OOS Sharpe = {r['sharpe']:+.3f} → {'PASS' if sharpe_ok else 'FAIL'} (need > 1.5)")
        out(f"  OOS N      = {r['n']}     → {'PASS' if n_ok else 'FAIL'} (need ≥ 30)")
        out(f"  OOS Bonf p = {t['oos_p_bonf']:.4f} → {'PASS' if p_ok else 'FAIL'} (need < 0.05)")
        out(f"  CANDIDATE: {'YES — fresh-data investigation flag' if flagged else 'no'}")
        if flagged:
            oos_net = trades.loc[
                (trades["cell"] == cell) & (trades["sample"] == "OOS"), "net_dollars"
            ].values
            sl, sm, sh = bootstrap_sharpe_ci(oos_net, sessions["OOS"])
            out(f"  Sharpe 95% bootstrap CI: [{sl:+.3f}, {sh:+.3f}], median {sm:+.3f}")
        candidates_data.append({
            "cell": cell, "flagged": flagged,
            "oos_sharpe": r["sharpe"], "oos_n": r["n"], "oos_p_bonf": t["oos_p_bonf"],
        })

    # Persist terminal log
    (OUT_DIR / "cell_summary_terminal.txt").write_text(buf.getvalue())
    print(f"\nSaved: {OUT_DIR / 'cell_stats.csv'}")
    print(f"Saved: {OUT_DIR / 'per_cell_tests.csv'}")
    print(f"Saved: {OUT_DIR / 'cell_summary_terminal.txt'}")


if __name__ == "__main__":
    main()
