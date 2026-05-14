"""Shared helpers for calendar conditioning scripts. Read-only utilities."""
from __future__ import annotations

import datetime as dt
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

DISCLOSURE = """\
This analysis is exploratory diagnostic work on a heavily consumed
corpus during an active forward test. It is NOT pre-registered.
Results CANNOT authorize modifications to OMEN's locked config or
pre-reg.

This is approximately the Nth diagnostic on this 504-trade corpus.
Project-wide false discovery rate is high. Time-of-day and OPEX
buckets are correlated with vol regime, so positive findings here
may overlap with the ATR/VIX regime findings from prior work
(commit b8880d6).

Any positive finding can only be honestly evaluated on a future
pre-registered forward window after OMEN-minus-SL verdict.
"""

REPO = Path("/Users/rafanelson/Omen")
IS_BUGFIX = REPO / "diagnostics/all-bugfixes-baseline/is_all_bugfixes.csv"
OOS_BUGFIX = REPO / "diagnostics/all-bugfixes-baseline/oos_all_bugfixes.csv"
OUT_DIR = REPO / "diagnostics/calendar"

ET = ZoneInfo("America/New_York")
SL_CELL = "SHORT_long"
N_INSUFFICIENT = 30


def load_trades() -> pd.DataFrame:
    is_df = pd.read_csv(IS_BUGFIX); is_df["sample"] = "IS"
    oos_df = pd.read_csv(OOS_BUGFIX); oos_df["sample"] = "OOS"
    df = pd.concat([is_df, oos_df], ignore_index=True)
    df["entry_time_utc"] = pd.to_datetime(df["entry_time"], utc=True)
    df["entry_time_et"] = df["entry_time_utc"].dt.tz_convert(ET)
    df["entry_date"] = df["entry_time_et"].dt.date
    df["entry_hour"] = df["entry_time_et"].dt.hour
    df["entry_minute"] = df["entry_time_et"].dt.minute
    df["weekday_name"] = df["entry_time_et"].dt.day_name()
    df["side_label"] = np.where(df["side"] == 1, "LONG", "SHORT")
    df["cell"] = df["side_label"] + "_" + df["gamma_regime"].astype(str)
    df = df.sort_values("entry_time_utc").reset_index(drop=True)
    return df


def max_dd(net: pd.Series, t: pd.Series) -> float:
    if len(net) == 0:
        return 0.0
    order = t.argsort()
    eq = np.cumsum(net.values[order])
    return float((eq - np.maximum.accumulate(eq)).min())


def sharpe(net: pd.Series, n_sessions: int) -> float | None:
    n = len(net)
    if n < 2 or n_sessions <= 0:
        return None
    tpd = n / n_sessions
    m = float(net.mean()); s = float(net.std(ddof=1))
    if s == 0:
        return None
    return ((m * tpd) / (s * np.sqrt(tpd))) * np.sqrt(252)


def group_stats(df: pd.DataFrame, label: str) -> dict:
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
             "sharpe": sharpe(net, n_sessions),
             "max_dd": max_dd(net, df["entry_time_utc"]),
             "n_sessions": int(n_sessions)}


def fmt(v, spec="+.2f"):
    if v is None or (isinstance(v, float) and (np.isnan(v) or np.isinf(v))):
        return "—"
    return f"{v:{spec}}"


def fmt_pf(v):
    if v is None or (isinstance(v, float) and np.isinf(v)):
        return "∞"
    if isinstance(v, float) and np.isnan(v):
        return "—"
    return f"{v:.2f}"


def print_group_table(stats_list: list[dict], title: str) -> None:
    print()
    print("=" * 80)
    print(title)
    print("=" * 80)
    print(f"  {'group':<40s}  {'N':>4s}  {'sum $':>10s}  {'win':>7s}  "
          f"{'avg win':>9s}  {'avg loss':>9s}  {'PF':>6s}  {'Sharpe':>7s}  "
          f"{'max DD':>10s}")
    for s in stats_list:
        if s["n"] == 0:
            print(f"  {s['label']:<40s}  empty"); continue
        flag = "*" if s["n"] < N_INSUFFICIENT else " "
        print(f"  {s['label']:<40s}  {s['n']:>3d}{flag}  ${s['sum']:>+9.0f}  "
              f"{s['win_rate']*100:>6.1f}%  "
              f"${s['avg_win']:>+8.2f}  ${s['avg_loss']:>+8.2f}  "
              f"{fmt_pf(s['profit_factor']):>6s}  {fmt(s['sharpe']):>7s}  "
              f"${s['max_dd']:>+9.0f}")
    print("  (* = N < 30, flagged insufficient sample)")


def md_group_table(stats_list: list[dict]) -> list[str]:
    L = []
    L.append("| group | N | sum $ | win | avg win | avg loss | PF | Sharpe (ann.) | max DD |")
    L.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for s in stats_list:
        if s["n"] == 0:
            L.append(f"| {s['label']} | 0 | — | — | — | — | — | — | — |")
            continue
        flag = " ⚠" if s["n"] < N_INSUFFICIENT else ""
        L.append(f"| {s['label']}{flag} | {s['n']} | ${s['sum']:+.0f} | "
                 f"{s['win_rate']*100:.1f}% | ${s['avg_win']:+.2f} | "
                 f"${s['avg_loss']:+.2f} | {fmt_pf(s['profit_factor'])} | "
                 f"{fmt(s['sharpe'])} | ${s['max_dd']:+.0f} |")
    L.append("")
    L.append("⚠ flag = N < 30, insufficient sample.")
    return L


def third_friday(year: int, month: int) -> dt.date:
    """Return the third Friday of (year, month)."""
    first = dt.date(year, month, 1)
    # Python: weekday() Mon=0 ... Fri=4
    days_to_friday = (4 - first.weekday()) % 7
    first_friday = first + dt.timedelta(days=days_to_friday)
    return first_friday + dt.timedelta(days=14)


def opex_week_dates(year: int, month: int) -> set[dt.date]:
    """Return all 5 Mon-Fri dates of OPEX week (week containing the third Friday)."""
    third_fri = third_friday(year, month)
    monday = third_fri - dt.timedelta(days=4)
    return {monday + dt.timedelta(days=i) for i in range(5)}


def is_opex_week(d: dt.date) -> bool:
    return d in opex_week_dates(d.year, d.month)
