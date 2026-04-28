"""Time-of-day stratification of locked Flow Burst baseline.

Tests whether the academic literature's intraday momentum pattern
(opening drive + closing drive peaks; midday lull) shows up in the
strategy's per-trade P&L. Read-only: consumes the existing locked
trade log; produces a CSV + markdown report.

References (background only — no actions taken):
- Baltussen, Da, Lammers, Martens (2021), "Hedging Demand and Market
  Intraday Momentum"
- Gao, Han, Li, Zhou (2018), "Market intraday momentum"
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd

BACKEND = Path("/Users/rafanelson/Omen/backend")
INPUT_CSV = BACKEND / "data" / "analysis" / "locked_baseline_trades_blackout_lunch.csv"
OUTPUT_CSV = BACKEND / "data" / "analysis" / "tod_slicing_results.csv"
OUTPUT_MD = BACKEND / "diagnostics" / "tod" / "REPORT.md"

# Buckets are half-open intervals on minute-of-day (hour*60 + minute) at
# entry_time. Order is preserved in output.
BUCKETS: list[tuple[str, int, int]] = [
    ("opening_drive", 9 * 60 + 30, 10 * 60),       # 09:30-09:59
    ("morning_2",     10 * 60,     10 * 60 + 30),  # 10:00-10:29
    ("lunch",         10 * 60 + 30, 12 * 60 + 30), # 10:30-12:29 (filter)
    ("afternoon_1",   12 * 60 + 30, 14 * 60),      # 12:30-13:59
    ("afternoon_2",   14 * 60,      15 * 60 + 30), # 14:00-15:29
    ("closing_drive", 15 * 60 + 30, 16 * 60 + 1),  # 15:30-16:00 inclusive
]
LOW_CONFIDENCE_N = 10


def stats_for(df: pd.DataFrame) -> dict:
    n = len(df)
    if n == 0:
        return {
            "n": 0, "win_rate": float("nan"),
            "mean_pnl": float("nan"), "median_pnl": float("nan"),
            "total_pnl": 0.0,
            "n_target": 0, "n_stop": 0, "n_time": 0, "n_session_close": 0,
            "per_trade_sharpe": float("nan"),
        }
    net = df["net_dollars"].astype(float)
    std = float(net.std(ddof=1)) if n >= 2 else float("nan")
    sharpe = float(net.mean() / std) if (std and std > 0) else float("nan")
    return {
        "n": n,
        "win_rate": float((net > 0).mean()),
        "mean_pnl": float(net.mean()),
        "median_pnl": float(net.median()),
        "total_pnl": float(net.sum()),
        "n_target": int((df["exit_reason"] == "target").sum()),
        "n_stop": int((df["exit_reason"] == "stop").sum()),
        "n_time": int((df["exit_reason"] == "time").sum()),
        "n_session_close": int((df["exit_reason"] == "session_close").sum()),
        "per_trade_sharpe": sharpe,
    }


def main() -> None:
    df = pd.read_csv(INPUT_CSV)
    if len(df) != 174:
        print(f"WARNING: expected 174 rows, got {len(df)}")

    # Use hour_min (minute-of-day at entry) — already in the CSV.
    mod = df["hour_min"].astype(int)

    rows: list[dict] = []
    for label, lo, hi in BUCKETS:
        mask = (mod >= lo) & (mod < hi)
        sub = df[mask]
        rec = {"bucket": label, "window": _fmt_window(lo, hi), **stats_for(sub)}
        rec["low_confidence"] = rec["n"] < LOW_CONFIDENCE_N
        rows.append(rec)

    # Sub-stratify closing_drive by gamma_regime
    cd_mask = (mod >= BUCKETS[-1][1]) & (mod < BUCKETS[-1][2])
    closing_df = df[cd_mask]
    cd_substrat: list[dict] = []
    for regime in ("long", "short"):
        sub = closing_df[closing_df["gamma_regime"] == regime]
        rec = {
            "bucket": f"closing_drive::{regime}_gamma",
            "window": _fmt_window(*BUCKETS[-1][1:]),
            **stats_for(sub),
        }
        rec["low_confidence"] = rec["n"] < LOW_CONFIDENCE_N
        cd_substrat.append(rec)

    main_df = pd.DataFrame(rows)
    sub_df = pd.DataFrame(cd_substrat)
    out = pd.concat([main_df, sub_df], ignore_index=True)
    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUTPUT_CSV, index=False)

    _print_table("Time-of-day buckets", main_df)
    _print_table("Closing drive — sub-stratified by gamma regime", sub_df)

    print(f"\nCSV: {OUTPUT_CSV}")

    md = _build_report(main_df, sub_df)
    OUTPUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_MD.write_text(md)
    print(f"REPORT: {OUTPUT_MD}")


def _fmt_window(lo: int, hi: int) -> str:
    def _hm(m: int) -> str:
        return f"{m // 60:02d}:{m % 60:02d}"
    return f"{_hm(lo)}-{_hm(hi - 1) if hi - 1 != hi else _hm(hi)}"


def _print_table(title: str, df: pd.DataFrame) -> None:
    print(f"\n=== {title} ===")
    if df.empty:
        print("(no rows)")
        return
    cols = ["bucket", "window", "n", "win_rate", "mean_pnl", "median_pnl",
            "total_pnl", "n_target", "n_stop", "n_time", "per_trade_sharpe",
            "low_confidence"]
    show = df[cols].copy()
    fmt = {
        "win_rate": (lambda v: "—" if pd.isna(v) else f"{v:.3f}"),
        "mean_pnl": (lambda v: "—" if pd.isna(v) else f"${v:,.2f}"),
        "median_pnl": (lambda v: "—" if pd.isna(v) else f"${v:,.2f}"),
        "total_pnl": (lambda v: f"${v:,.2f}"),
        "per_trade_sharpe": (lambda v: "—" if pd.isna(v) else f"{v:+.4f}"),
    }
    for col, fn in fmt.items():
        show[col] = show[col].map(fn)
    print(show.to_string(index=False))


def _md_table(df: pd.DataFrame) -> str:
    cols = ["bucket", "window", "n", "win_rate", "mean_pnl", "median_pnl",
            "total_pnl", "n_target", "n_stop", "n_time", "per_trade_sharpe",
            "low_confidence"]
    out = ["| " + " | ".join(cols) + " |",
           "|" + "|".join(["---" if c in ("bucket", "window", "low_confidence") else "---:" for c in cols]) + "|"]
    for _, r in df[cols].iterrows():
        cells = []
        for c in cols:
            v = r[c]
            if pd.isna(v):
                cells.append("—")
            elif c == "win_rate":
                cells.append(f"{v:.3f}")
            elif c in ("mean_pnl", "median_pnl", "total_pnl"):
                cells.append(f"${v:,.2f}")
            elif c == "per_trade_sharpe":
                cells.append(f"{v:+.4f}")
            elif c == "low_confidence":
                cells.append("yes" if v else "no")
            else:
                cells.append(str(int(v)) if isinstance(v, (int, np.integer, float)) and not isinstance(v, bool) else str(v))
        out.append("| " + " | ".join(cells) + " |")
    return "\n".join(out)


def _build_report(main_df: pd.DataFrame, sub_df: pd.DataFrame) -> str:
    open_row = main_df[main_df["bucket"] == "opening_drive"].iloc[0]
    close_row = main_df[main_df["bucket"] == "closing_drive"].iloc[0]
    open_n, close_n = int(open_row["n"]), int(close_row["n"])
    open_exp = float(open_row["mean_pnl"])
    close_exp = float(close_row["mean_pnl"]) if close_n > 0 else float("nan")
    open_total = float(open_row["total_pnl"])
    close_total = float(close_row["total_pnl"])

    # Verdict logic for the closing-drive hypothesis specifically:
    if close_n == 0:
        verdict = "INCONCLUSIVE"
        verdict_reason = (
            f"Closing-drive bucket has n=0 — strategy emits no entries in 15:30–16:00 ET, "
            f"so the literature's predicted second peak cannot be evaluated on this data. "
            f"The end-of-session entry runway gate (`min_bars_runway` = time_stop_min/bar_freq + 1) "
            f"caps the latest-allowed entry around 15:30 ET at 5min/25min, "
            f"making this bucket structurally near-empty for the locked params."
        )
    elif close_n < LOW_CONFIDENCE_N:
        # Direction-of-effect check at low confidence
        ratio = close_exp / open_exp if (open_exp not in (0, float("nan")) and open_exp > 0) else float("nan")
        verdict = "INCONCLUSIVE"
        verdict_reason = (
            f"Closing-drive bucket has n={close_n} (< {LOW_CONFIDENCE_N}); too few trades to "
            f"confirm or kill the closing-drive hypothesis. "
            f"Observed mean P&L in closing_drive = ${close_exp:,.2f} vs opening_drive ${open_exp:,.2f} "
            f"(ratio {ratio:.2f}), but at this sample size the standard error is dominant."
        )
    else:
        if close_exp >= 0.5 * open_exp:
            verdict = "CONFIRMS"
            verdict_reason = (
                f"Closing-drive expectancy ${close_exp:,.2f} is ≥ 50% of opening-drive "
                f"expectancy ${open_exp:,.2f} on adequate sample size (n={close_n}), "
                f"consistent with the literature's prediction of a second intraday peak."
            )
        elif close_exp <= 0:
            verdict = "CONTRADICTS"
            verdict_reason = (
                f"Closing-drive expectancy ${close_exp:,.2f} is non-positive on adequate "
                f"sample size (n={close_n}); does not show the predicted second peak."
            )
        else:
            verdict = "INCONCLUSIVE"
            verdict_reason = (
                f"Closing-drive expectancy ${close_exp:,.2f} is positive but materially "
                f"below opening-drive ${open_exp:,.2f} (n={close_n}); ambiguous."
            )

    parts = []
    parts.append("# Time-of-day stratification — Flow Burst locked baseline\n")
    parts.append("## Summary\n")
    parts.append(
        f"On 174 trades from the locked Dec 2025 – Apr 2026 baseline, the opening-drive "
        f"bucket (09:30–09:59) holds **n={open_n}** trades with mean P&L "
        f"**${open_exp:,.2f}** and total **${open_total:,.2f}**. The closing-drive bucket "
        f"(15:30–16:00) holds **n={close_n}** trades"
        + (f" with mean P&L **${close_exp:,.2f}** and total **${close_total:,.2f}**.\n"
           if close_n > 0 else " — empty.\n")
    )
    parts.append("## Buckets\n")
    parts.append(_md_table(main_df))
    parts.append("\n## Closing drive — sub-stratified by gamma regime\n")
    parts.append(_md_table(sub_df))
    parts.append("\n## Comparison vs literature prediction\n")
    parts.append(
        "Baltussen et al (2021) and Gao, Han, Li, Zhou (2018) document a **U-shaped intraday "
        "momentum profile** in equity index futures: an opening-drive peak (driven by "
        "overnight information assimilation and dealer hedging at the open), a midday lull, "
        "and a **closing-drive peak** in the last 30 minutes (driven by late-day rebalancing "
        "and end-of-day delta hedging by option dealers). The hypothesis under test: the "
        "Flow Burst signal — which keys off `gexoflow_z` / `dexoflow_z` z-score spikes — "
        "should also show elevated expectancy in the 15:30–16:00 closing-drive window if "
        "the underlying flow signal captures dealer-hedging activity, not just open-drive "
        "information flow.\n"
    )
    parts.append(
        f"**Observed:**  opening_drive n={open_n}, mean ${open_exp:,.2f}; "
        f"closing_drive n={close_n}"
        + (f", mean ${close_exp:,.2f}.\n" if close_n > 0 else " (empty bucket).\n")
    )
    parts.append(f"\n## Verdict: **{verdict}**\n")
    parts.append(verdict_reason + "\n")
    parts.append(
        f"\nLow-confidence flag threshold: any bucket with n < {LOW_CONFIDENCE_N} is "
        "marked `low_confidence: yes` in the tables and should not be used for inference.\n"
    )
    return "\n".join(parts)


if __name__ == "__main__":
    main()
