"""TRCB-v2 Phase 3 — apply v2 filter to OMEN trade log.

THROWAWAY IN-SAMPLE ANALYSIS. See common.CRITICAL_DISCLOSURE.

For each trade in the concatenated IS+OOS OMEN log:
  - T = entry_time (= signal bar close per backtest.py:197 convention)
  - Evaluate P2/P3/P4 v2 predicates AT THE TRADE'S DIRECTION
  - P2 baseline: trailing-100-bar median of 30s directional volume
  - P4 threshold: PRICE_ATR_MULT × atr_at_entry (from the trade log itself)
  - FILTER_CONFIRMED iff all three predicates pass in the trade's direction

Report metrics on BOTH arms:
  - Full OMEN trade log (174 IS + 158 OOS = 332 trades)
  - OMEN-minus-SL (exclude side=-1 & gamma_regime="long" cells)

For each arm × sample (IS / OOS / Combined) × subset (all / confirmed / rejected):
  N, win_rate, mean_net_dollars, sum_net_dollars, sharpe, max_drawdown.
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (  # noqa: E402
    BAR_FREQ, CRITICAL_DISCLOSURE, DELTA_RATIO, DIVISOR_FLOOR, ES_1S_PATH,
    OUTPUT_ANALYSIS_DIR, PER_BAR_VOLUMES_PATH, PHASE3_RESULTS_CSV,
    PRICE_ATR_MULT, TIMEZONE, TRAILING_MEDIAN_BARS, VOLUME_MULT,
    WINDOW_SECONDS, load_trade_log,
)

SL_CELL = "SHORT_long"  # side=-1 & gamma_regime="long"
REPORT_MD = OUTPUT_ANALYSIS_DIR / "phase3_summary_report.md"


def _max_drawdown(net_dollars: pd.Series, entry_time: pd.Series) -> float:
    """Cumulative-sum max drawdown ordered by entry_time."""
    if len(net_dollars) == 0:
        return 0.0
    order = entry_time.argsort()
    eq = np.cumsum(net_dollars.values[order])
    peak = np.maximum.accumulate(eq)
    return float((eq - peak).min())


def _sharpe(net: pd.Series, n_sessions: int) -> float:
    """Per-trade → daily → annualized Sharpe (mirrors cell_analysis.cell_sharpe)."""
    n = len(net)
    if n < 2 or n_sessions <= 0:
        return float("nan")
    tpd = n / n_sessions
    if tpd <= 0:
        return float("nan")
    mean_t = float(net.mean()); std_t = float(net.std(ddof=1))
    if std_t == 0:
        return float("nan")
    return ((mean_t * tpd) / (std_t * np.sqrt(tpd))) * np.sqrt(252)


def _summarize_subset(trades: pd.DataFrame, sessions_in_sample: int) -> dict:
    if len(trades) == 0:
        return {"n": 0, "win_rate": float("nan"), "mean": 0.0, "sum": 0.0,
                "sharpe": float("nan"), "max_dd": 0.0}
    net = trades["net_dollars"]
    return {
        "n": int(len(trades)),
        "win_rate": float((net > 0).mean()),
        "mean": float(net.mean()),
        "sum": float(net.sum()),
        "sharpe": _sharpe(net, sessions_in_sample),
        "max_dd": _max_drawdown(net, trades["entry_time_utc"]),
    }


def _build_per_bar_signals() -> pd.DataFrame:
    """Compute v2 P2/P3 signals for every RTH 5-min bar in per_bar_volumes_30s.

    Returns df indexed by bar_close_et with cols:
      dir_buy_vol_30s, dir_sell_vol_30s,
      median_buy_100, median_sell_100,
      p2_long, p2_short, p3_long, p3_short
    """
    bv = pd.read_parquet(PER_BAR_VOLUMES_PATH)
    if not isinstance(bv["bar_close_utc"].dtype, pd.DatetimeTZDtype):
        bv["bar_close_utc"] = pd.to_datetime(bv["bar_close_utc"], utc=True)
    bv["bar_close_et"] = bv["bar_close_utc"].dt.tz_convert(TIMEZONE)
    bv["session_date"] = pd.to_datetime(bv["session_date"]).dt.date
    bv = bv.sort_values("bar_close_utc").reset_index(drop=True)

    bv["median_buy_100"] = bv["dir_buy_vol_30s"].rolling(
        TRAILING_MEDIAN_BARS, min_periods=TRAILING_MEDIAN_BARS
    ).median().shift(1)
    bv["median_sell_100"] = bv["dir_sell_vol_30s"].rolling(
        TRAILING_MEDIAN_BARS, min_periods=TRAILING_MEDIAN_BARS
    ).median().shift(1)

    bv["p2_long"] = bv["dir_buy_vol_30s"] >= (VOLUME_MULT * bv["median_buy_100"])
    bv["p2_short"] = bv["dir_sell_vol_30s"] >= (VOLUME_MULT * bv["median_sell_100"])
    denom_long = bv["dir_sell_vol_30s"].clip(lower=DIVISOR_FLOOR)
    denom_short = bv["dir_buy_vol_30s"].clip(lower=DIVISOR_FLOOR)
    bv["delta_ratio_long"] = bv["dir_buy_vol_30s"] / denom_long
    bv["delta_ratio_short"] = bv["dir_sell_vol_30s"] / denom_short
    bv["p3_long"] = bv["delta_ratio_long"] >= DELTA_RATIO
    bv["p3_short"] = bv["delta_ratio_short"] >= DELTA_RATIO
    return bv.set_index("bar_close_et")


def _evaluate_p4(trades: pd.DataFrame, es_1s: pd.DataFrame) -> pd.DataFrame:
    """Add price_at_T, price_at_T_plus_30s, price_move_30s, p4_long, p4_short."""
    out = trades.copy()
    T_idx = pd.DatetimeIndex(out["entry_time_et"])
    out["price_at_T"] = es_1s["close"].reindex(
        T_idx, method="ffill", tolerance=pd.Timedelta("5s")
    ).values
    target = pd.DatetimeIndex(out["entry_time_et"] + pd.Timedelta(seconds=WINDOW_SECONDS))
    out["price_at_T_plus_30s"] = es_1s["close"].reindex(
        target, method="ffill", tolerance=pd.Timedelta("5s")
    ).values
    out["price_move_30s"] = out["price_at_T_plus_30s"] - out["price_at_T"]
    out["p4_threshold"] = PRICE_ATR_MULT * out["atr_at_entry"]
    out["p4_long"] = out["price_move_30s"] >= out["p4_threshold"]
    out["p4_short"] = (-out["price_move_30s"]) >= out["p4_threshold"]
    return out


def main() -> None:
    OUTPUT_ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)
    print(CRITICAL_DISCLOSURE)
    print("=" * 72)
    print("TRCB-v2 PHASE 3 — OMEN TRADE FILTER (IN-SAMPLE)")
    print("=" * 72)
    print(f"  WINDOW_SECONDS = {WINDOW_SECONDS}, DELTA_RATIO = {DELTA_RATIO}\n")

    # ---- Load trade log + ES 1s + per-bar signals ----
    trades = load_trade_log()
    print(f"trades: total={len(trades)}  IS={int((trades['sample']=='IS').sum())}  "
          f"OOS={int((trades['sample']=='OOS').sum())}")

    es_1s = pd.read_parquet(ES_1S_PATH, columns=["close"])
    if not isinstance(es_1s.index.dtype, pd.DatetimeTZDtype):
        es_1s.index = pd.to_datetime(es_1s.index, utc=True).tz_convert(TIMEZONE)
    print(f"ES 1s rows: {len(es_1s):,}")

    bar_sig = _build_per_bar_signals()
    print(f"bar signals: {len(bar_sig):,} rows ({bar_sig['session_date'].nunique()} sessions)")

    # ---- Lookup P2/P3 per trade at entry_time_et ----
    # bar_sig is indexed by bar_close_et tz-aware ET; trades.entry_time_et is the same.
    sig_cols = ["dir_buy_vol_30s", "dir_sell_vol_30s",
                "median_buy_100", "median_sell_100",
                "delta_ratio_long", "delta_ratio_short",
                "p2_long", "p2_short", "p3_long", "p3_short"]
    trades = trades.set_index("entry_time_et", drop=False)
    for c in sig_cols:
        trades[c] = bar_sig[c].reindex(trades.index)
    trades = trades.reset_index(drop=True)

    n_missing_sig = int(trades["median_buy_100"].isna().sum())
    if n_missing_sig:
        print(f"  [WARN] {n_missing_sig} trades have no v2 signal (trailing-median NaN OR "
              f"bar not found in per_bar_volumes_30s)")

    # ---- Evaluate P4 ----
    trades = _evaluate_p4(trades, es_1s)
    n_missing_p4 = int(trades["price_at_T"].isna().sum())
    if n_missing_p4:
        print(f"  [WARN] {n_missing_p4} trades have no price at entry_time (1s ES lookup miss)")

    # ---- Direction-specific confirmation ----
    trades["trcb_long"] = (trades["p2_long"] & trades["p3_long"] & trades["p4_long"]).fillna(False)
    trades["trcb_short"] = (trades["p2_short"] & trades["p3_short"] & trades["p4_short"]).fillna(False)
    is_long = trades["side"] == 1
    is_short = trades["side"] == -1
    trades["FILTER_CONFIRMED"] = (
        (is_long & trades["trcb_long"]) | (is_short & trades["trcb_short"])
    )
    trades["FILTER_EVALUABLE"] = (
        trades["median_buy_100"].notna() & trades["price_at_T"].notna()
    )

    print(f"\nFILTER_CONFIRMED counts:")
    print(f"  total       : {int(trades['FILTER_CONFIRMED'].sum())} / {len(trades)} "
          f"({trades['FILTER_CONFIRMED'].mean()*100:.1f}%)")
    print(f"  IS          : "
          f"{int(((trades['sample']=='IS') & trades['FILTER_CONFIRMED']).sum())} / "
          f"{int((trades['sample']=='IS').sum())}")
    print(f"  OOS         : "
          f"{int(((trades['sample']=='OOS') & trades['FILTER_CONFIRMED']).sum())} / "
          f"{int((trades['sample']=='OOS').sum())}")

    # ---- Both-arm summary tables ----
    arms = {
        "full_omen": trades,
        "omen_minus_sl": trades[trades["cell"] != SL_CELL].copy(),
    }
    summary_rows = []
    for arm_name, arm_df in arms.items():
        for samp in ("IS", "OOS", "Combined"):
            if samp == "Combined":
                sub = arm_df
            else:
                sub = arm_df[arm_df["sample"] == samp]
            n_sessions = int(sub["entry_date"].nunique() if "entry_date" in sub.columns
                              else sub["entry_time_et"].dt.date.nunique())
            for subset_name, mask in (
                ("all",       pd.Series(True, index=sub.index)),
                ("confirmed", sub["FILTER_CONFIRMED"]),
                ("rejected",  ~sub["FILTER_CONFIRMED"]),
            ):
                trd = sub[mask]
                st = _summarize_subset(trd, n_sessions)
                summary_rows.append({
                    "arm": arm_name, "sample": samp, "subset": subset_name,
                    "n_sessions": n_sessions, **st,
                })

    summary_df = pd.DataFrame(summary_rows)

    # ---- Print summary tables ----
    print("\n" + "=" * 72)
    print("SUMMARY — both arms × IS/OOS/Combined × all/confirmed/rejected")
    print("=" * 72)
    fmt = "{arm:<14s} {sample:<8s} {subset:<10s}  n={n:>3d}  win={win:>6.1%}  " \
          "mean=${mean:>+7.2f}  sum=${sum:>+9.0f}  Sharpe={sharpe:>+6.2f}  DD=${dd:>+9.0f}"
    for arm in ("full_omen", "omen_minus_sl"):
        print(f"\n--- {arm} ---")
        for samp in ("IS", "OOS", "Combined"):
            for subs in ("all", "confirmed", "rejected"):
                r = summary_df[(summary_df["arm"] == arm) & (summary_df["sample"] == samp)
                                 & (summary_df["subset"] == subs)].iloc[0]
                wr = r["win_rate"] if pd.notna(r["win_rate"]) else 0
                sh = r["sharpe"] if pd.notna(r["sharpe"]) else 0
                print(fmt.format(arm=arm, sample=samp, subset=subs,
                                 n=int(r["n"]), win=wr,
                                 mean=r["mean"], sum=r["sum"],
                                 sharpe=sh, dd=r["max_dd"]))

    # ---- Persist ----
    # Trade-level CSV
    keep = ["sample", "strategy", "side", "side_label", "cell", "gamma_regime",
            "entry_time", "entry_px", "exit_time", "exit_reason", "atr_at_entry",
            "gross_points", "net_dollars",
            "dir_buy_vol_30s", "dir_sell_vol_30s",
            "median_buy_100", "median_sell_100",
            "delta_ratio_long", "delta_ratio_short",
            "p2_long", "p2_short", "p3_long", "p3_short",
            "price_at_T", "price_at_T_plus_30s", "price_move_30s", "p4_threshold",
            "p4_long", "p4_short",
            "trcb_long", "trcb_short",
            "FILTER_EVALUABLE", "FILTER_CONFIRMED"]
    trades[keep].to_csv(PHASE3_RESULTS_CSV, index=False)
    print(f"\nSaved trade-level CSV: {PHASE3_RESULTS_CSV}")

    # Summary CSV (one row per arm × sample × subset)
    summary_csv = OUTPUT_ANALYSIS_DIR / "phase3_summary_table.csv"
    summary_df.to_csv(summary_csv, index=False)
    print(f"Saved summary CSV    : {summary_csv}")

    # Markdown report
    REPORT_MD.write_text(_build_report(summary_df, trades))
    print(f"Saved markdown report: {REPORT_MD}")


def _md_row(r: pd.Series) -> str:
    wr = f"{r['win_rate']*100:.1f}%" if pd.notna(r["win_rate"]) else "—"
    sh = f"{r['sharpe']:+.2f}" if pd.notna(r["sharpe"]) else "—"
    return (f"| {r['arm']} | {r['sample']} | {r['subset']} | {int(r['n'])} | "
            f"{wr} | ${r['mean']:+.2f} | ${r['sum']:+.0f} | {sh} | "
            f"${r['max_dd']:+.0f} |")


def _build_report(summary_df: pd.DataFrame, trades: pd.DataFrame) -> str:
    parts: list[str] = []
    parts.append("# TRCB-v2 Phase 3 — OMEN Trade Filter (IN-SAMPLE, THROWAWAY)\n")
    parts.append(CRITICAL_DISCLOSURE)
    parts.append("")
    parts.append(f"**Generated:** {datetime.now().isoformat(timespec='seconds')}")
    parts.append(f"**Branch:** `analysis/trcb-v2-consumed-data-test-throwaway`\n")
    parts.append("## Setup\n")
    parts.append(f"- Trades: {len(trades)} "
                 f"(IS={int((trades['sample']=='IS').sum())}, "
                 f"OOS={int((trades['sample']=='OOS').sum())})")
    parts.append(f"- Filter params: WINDOW=30s, VOL_MULT=1.0, DELTA_RATIO=1.5, "
                 f"PRICE_ATR=0.25, ATR=14")
    parts.append("- P4 uses `atr_at_entry` directly from the trade log "
                 "(OMEN's SMA(14) ATR), not the Phase-2 Wilder ATR.")
    parts.append("- P2 baseline uses trailing-100-bar median of 30s directional "
                 "volume from per_bar_volumes_30s.")
    parts.append("- `FILTER_CONFIRMED` = trade's direction matches a v2 trigger at T.\n")

    parts.append("## Filter-pass counts")
    n_total = len(trades)
    n_conf = int(trades["FILTER_CONFIRMED"].sum())
    n_eval = int(trades["FILTER_EVALUABLE"].sum())
    parts.append(f"- Total trades              : **{n_total}**")
    parts.append(f"- Evaluable                 : {n_eval}")
    parts.append(f"- FILTER_CONFIRMED          : **{n_conf}** ({n_conf/n_total*100:.1f}% of total)")
    parts.append(f"- IS confirmed              : "
                 f"{int(((trades['sample']=='IS') & trades['FILTER_CONFIRMED']).sum())} / "
                 f"{int((trades['sample']=='IS').sum())}")
    parts.append(f"- OOS confirmed             : "
                 f"{int(((trades['sample']=='OOS') & trades['FILTER_CONFIRMED']).sum())} / "
                 f"{int((trades['sample']=='OOS').sum())}\n")

    parts.append("## Performance table — both arms × IS/OOS/Combined × all/confirmed/rejected\n")
    parts.append("| arm | sample | subset | N | win | mean | sum | Sharpe | max DD |")
    parts.append("|---|---|---|---:|---:|---:|---:|---:|---:|")
    for arm in ("full_omen", "omen_minus_sl"):
        for samp in ("IS", "OOS", "Combined"):
            for subs in ("all", "confirmed", "rejected"):
                r = summary_df[(summary_df["arm"] == arm) & (summary_df["sample"] == samp)
                                 & (summary_df["subset"] == subs)].iloc[0]
                parts.append(_md_row(r))
    parts.append("")

    parts.append("## Read-with-caution notes\n")
    parts.append("- See CRITICAL DISCLOSURE above. **In-sample.** Positive findings do not validate the framework.")
    parts.append("- `omen_minus_sl` excludes the `SHORT_long` cell, the worst-performing OOS cell in the prior cell-breakdown analysis (also throwaway, also in-sample selection).")
    parts.append("- A meaningful read: comparing **confirmed vs rejected** Sharpe *within a single arm × sample*. If FILTER_CONFIRMED trades systematically outperform FILTER_REJECTED on the same data, that's consistent with v2 measuring something — but cannot distinguish 'real edge' from 'curve-fit to this data'.")
    parts.append("- Small subset sizes (especially OOS confirmed) make Sharpe estimates noisy.")
    return "\n".join(parts) + "\n"


if __name__ == "__main__":
    main()
