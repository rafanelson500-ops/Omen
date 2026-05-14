"""Step 2 — VIX-conditioned analysis on all 504 bugfixed trades.

Joins vix_daily_full.csv (NOT vix_daily.csv) to the 504-trade log
on session date. Terciles on eligible trades.
"""
from __future__ import annotations

from datetime import datetime
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

VIX_CAVEAT = """\
VIX is daily close — session-level granularity only. Not intraday
vol state at entry. ATR conditioning is more directly relevant for
a 25-minute ES hold. VIX results are a cross-asset regime check,
not a within-instrument vol measure.
"""

REPO = Path("/Users/rafanelson/Omen")
IS_BUGFIX = REPO / "diagnostics/all-bugfixes-baseline/is_all_bugfixes.csv"
OOS_BUGFIX = REPO / "diagnostics/all-bugfixes-baseline/oos_all_bugfixes.csv"
VIX_FULL = REPO / "backend/data/analysis/vix_daily_full.csv"
OUT_MD = REPO / "diagnostics/vol-regime/02_vix_conditioning.md"

ET = ZoneInfo("America/New_York")
SL_CELL = "SHORT_long"


def _load_trades() -> pd.DataFrame:
    is_df = pd.read_csv(IS_BUGFIX); is_df["sample"] = "IS"
    oos_df = pd.read_csv(OOS_BUGFIX); oos_df["sample"] = "OOS"
    df = pd.concat([is_df, oos_df], ignore_index=True)
    df["entry_time_utc"] = pd.to_datetime(df["entry_time"], utc=True)
    df["entry_date"] = df["entry_time_utc"].dt.tz_convert(ET).dt.date
    df["side_label"] = np.where(df["side"] == 1, "LONG", "SHORT")
    df["cell"] = df["side_label"] + "_" + df["gamma_regime"].astype(str)
    return df


def _max_dd(net, t):
    if len(net) == 0:
        return 0.0
    order = t.argsort()
    eq = np.cumsum(net.values[order])
    return float((eq - np.maximum.accumulate(eq)).min())


def _sharpe(net, n_sessions):
    n = len(net)
    if n < 2 or n_sessions <= 0:
        return None
    tpd = n / n_sessions
    m = float(net.mean()); s = float(net.std(ddof=1))
    if s == 0:
        return None
    return ((m * tpd) / (s * np.sqrt(tpd))) * np.sqrt(252)


def _group_stats(df, label):
    n = len(df)
    if n == 0:
        return {"label": label, "n": 0}
    net = df["net_dollars"]
    wins = net[net > 0]; losses = net[net <= 0]
    avg_win = float(wins.mean()) if len(wins) else 0.0
    avg_loss = float(losses.mean()) if len(losses) else 0.0
    gross_p = float(wins.sum()) if len(wins) else 0.0
    gross_l = abs(float(losses.sum())) if len(losses) else 0.0
    pf = gross_p / gross_l if gross_l > 0 else (float("inf") if gross_p > 0 else 0.0)
    n_sessions = df["entry_date"].nunique()
    return {"label": label, "n": n, "sum": float(net.sum()),
             "win_rate": float((net > 0).mean()),
             "avg_win": avg_win, "avg_loss": avg_loss,
             "profit_factor": pf,
             "sharpe": _sharpe(net, n_sessions),
             "max_dd": _max_dd(net, df["entry_time_utc"]),
             "n_sessions": int(n_sessions)}


def _fmt(v, fmt="+.2f"):
    if v is None or (isinstance(v, float) and (np.isnan(v) or np.isinf(v))):
        return "—"
    return f"{v:{fmt}}"


def main() -> int:
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    print(DISCLOSURE)
    print("=" * 78)
    print("STEP 2 — VIX-conditioned analysis (504 trades)")
    print("=" * 78)

    trades = _load_trades()
    print(f"\nTrades: {len(trades)} ({trades['entry_date'].nunique()} sessions)")

    vix = pd.read_csv(VIX_FULL)
    vix["date"] = pd.to_datetime(vix["date"]).dt.date
    print(f"VIX rows: {len(vix)} (range {vix['date'].min()} → {vix['date'].max()})")

    # Fresh join: trades.entry_date ↔ vix.date
    trades = trades.merge(vix, how="left", left_on="entry_date", right_on="date")
    trades["vix_unavailable"] = trades["vix_close"].isna()
    n_excluded = int(trades["vix_unavailable"].sum())
    print(f"VIX unavailable: {n_excluded} / {len(trades)}")

    eligible = trades[~trades["vix_unavailable"]].copy()
    if len(eligible) == 0:
        print("[FATAL] no eligible trades."); return 1

    vc = eligible["vix_close"]
    print(f"\nVIX distribution on eligible (n={len(eligible)}):")
    print(f"  min={vc.min():.2f}  p25={vc.quantile(0.25):.2f}  "
          f"median={vc.median():.2f}  p75={vc.quantile(0.75):.2f}  "
          f"max={vc.max():.2f}")

    low_b = float(vc.quantile(1/3))
    high_b = float(vc.quantile(2/3))
    print(f"\nTercile boundaries (LOCKED):")
    print(f"  low_vix_boundary  (33rd pct): {low_b:.4f}")
    print(f"  high_vix_boundary (67th pct): {high_b:.4f}")

    eligible["vix_regime"] = pd.cut(
        eligible["vix_close"], bins=[-np.inf, low_b, high_b, np.inf],
        labels=["Low-VIX", "Mid-VIX", "High-VIX"]
    ).astype(str)

    groups = {
        "A: All 504 trades (incl. excluded)": trades,
        "B: Low-VIX (eligible)": eligible[eligible["vix_regime"] == "Low-VIX"],
        "C: Mid-VIX (eligible)": eligible[eligible["vix_regime"] == "Mid-VIX"],
        "D: High-VIX (eligible)": eligible[eligible["vix_regime"] == "High-VIX"],
        "E: minus-SL ∩ Low-VIX": eligible[(eligible["vix_regime"] == "Low-VIX")
                                            & (eligible["cell"] != SL_CELL)],
        "F: minus-SL ∩ High-VIX": eligible[(eligible["vix_regime"] == "High-VIX")
                                             & (eligible["cell"] != SL_CELL)],
    }
    stats = [_group_stats(g, lbl) for lbl, g in groups.items()]

    print()
    print("=" * 78)
    print("VIX REGIME COMPARISON")
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

    L: list[str] = []
    L.append("# Step 2 — VIX-conditioned analysis (504 trades)\n")
    L.append("Branch: `analysis/vol-regime-conditioning-throwaway` (throwaway).")
    L.append(f"Generated: {datetime.now().isoformat(timespec='seconds')}\n")
    L.append("## Disclosure\n")
    L.append("```")
    L.append(DISCLOSURE)
    L.append("```\n")
    L.append("## VIX caveat\n")
    L.append("```")
    L.append(VIX_CAVEAT)
    L.append("```\n")

    L.append("## Setup\n")
    L.append(f"- Trade pool: **{len(trades)} trades**, "
             f"**{trades['entry_date'].nunique()} sessions**, "
             f"{trades['entry_date'].min()} → {trades['entry_date'].max()}.")
    L.append(f"- VIX source: `backend/data/analysis/vix_daily_full.csv` "
             f"(CBOE public CSV, 175 rows, range "
             f"{vix['date'].min()} → {vix['date'].max()}).")
    L.append("- Join: on session date. VIX close from the trade's session date.")
    L.append("")

    L.append("## Eligibility\n")
    L.append(f"- Eligible : **{len(eligible)}**")
    L.append(f"- Excluded : **{n_excluded}** (VIX unavailable for session)")
    L.append("")
    L.append("## VIX distribution (eligible)\n")
    L.append(f"- n      : {len(eligible)}")
    L.append(f"- min    : {vc.min():.2f}")
    L.append(f"- p25    : {vc.quantile(0.25):.2f}")
    L.append(f"- median : {vc.median():.2f}")
    L.append(f"- p75    : {vc.quantile(0.75):.2f}")
    L.append(f"- max    : {vc.max():.2f}")
    L.append("")
    L.append("## Tercile boundaries (LOCKED for future pre-reg)\n")
    L.append(f"- `low_vix_boundary`  (33rd pct) = **{low_b:.4f}**")
    L.append(f"- `high_vix_boundary` (67th pct) = **{high_b:.4f}**")
    L.append("")
    L.append("## Group metrics\n")
    L.append("| group | N | sum $ | win | avg win | avg loss | PF | Sharpe (ann.) | max DD |")
    L.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for s in stats:
        if s["n"] == 0:
            L.append(f"| {s['label']} | 0 | — | — | — | — | — | — | — |")
            continue
        L.append(f"| {s['label']} | {s['n']} | ${s['sum']:+.0f} | "
                 f"{s['win_rate']*100:.1f}% | ${s['avg_win']:+.2f} | "
                 f"${s['avg_loss']:+.2f} | {s['profit_factor']:.2f} | "
                 f"{_fmt(s['sharpe'])} | ${s['max_dd']:+.0f} |")
    L.append("")

    OUT_MD.write_text("\n".join(L) + "\n")
    print(f"\nSaved: {OUT_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
