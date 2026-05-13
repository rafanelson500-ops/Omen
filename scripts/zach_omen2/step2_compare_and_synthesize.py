"""Step 2 — head-to-head comparison: locked bugfixed baseline vs Zach Omen 2.0.

Reads:
  diagnostics/all-bugfixes-baseline/is_all_bugfixes.csv  (locked IS, 257)
  diagnostics/all-bugfixes-baseline/oos_all_bugfixes.csv (locked OOS, 247)
  analysis/zach-omen2/zach_is_trades.csv  (Zach IS)
  analysis/zach-omen2/zach_oos_trades.csv (Zach OOS)
"""
from __future__ import annotations

import sys
from datetime import datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

REPO = Path("/Users/rafanelson/Omen")
LOCKED_DIR = REPO / "diagnostics/all-bugfixes-baseline"
ZACH_DIR = REPO / "analysis/zach-omen2"
ET = ZoneInfo("America/New_York")

LOCKED_IS = LOCKED_DIR / "is_all_bugfixes.csv"
LOCKED_OOS = LOCKED_DIR / "oos_all_bugfixes.csv"
ZACH_IS = ZACH_DIR / "zach_is_trades.csv"
ZACH_OOS = ZACH_DIR / "zach_oos_trades.csv"
OUT_MD = ZACH_DIR / "SYNTHESIS.md"

SL_CELL = "SHORT_long"
CELLS = ["LONG_long", "LONG_short", "SHORT_long", "SHORT_short"]
TRADE_START_TIME = time(12, 30)


def _load(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["entry_time"] = pd.to_datetime(df["entry_time"], utc=True)
    df["entry_time_utc"] = df["entry_time"]
    df["entry_time_et"] = df["entry_time"].dt.tz_convert(ET)
    df["exit_time"] = pd.to_datetime(df["exit_time"], utc=True)
    df["exit_time_et"] = df["exit_time"].dt.tz_convert(ET)
    df["entry_date"] = df["entry_time_et"].dt.date
    df["side_label"] = np.where(df["side"] == 1, "LONG", "SHORT")
    df["cell"] = df["side_label"] + "_" + df["gamma_regime"].astype(str)
    df["entry_t"] = df["entry_time_et"].dt.time
    df["before_1230"] = df["entry_t"].apply(lambda t: t < TRADE_START_TIME)
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


def _stats(df: pd.DataFrame, n_sessions: int) -> dict:
    if len(df) == 0:
        return {"n": 0, "win_rate": None, "mean": 0.0, "sum": 0.0,
                "sharpe": None, "max_dd": 0.0, "mean_bars_held": None}
    net = df["net_dollars"]
    return {
        "n": int(len(df)),
        "win_rate": float((net > 0).mean()),
        "mean": float(net.mean()),
        "sum": float(net.sum()),
        "sharpe": _sharpe(net, n_sessions),
        "max_dd": _max_dd(net, df["entry_time_utc"]),
        "mean_bars_held": float(df["bars_held"].mean()) if "bars_held" in df.columns else None,
    }


def _per_cell(df, n_sessions):
    return {c: _stats(df[df["cell"] == c], n_sessions) for c in CELLS}


def _fmt_sh(sh): return "—" if sh is None else f"{sh:+.2f}"
def _fmt_wr(wr): return "—" if wr is None else f"{wr*100:.1f}%"


def main() -> int:
    L_is = _load(LOCKED_IS);  L_oos = _load(LOCKED_OOS)
    Z_is = _load(ZACH_IS);    Z_oos = _load(ZACH_OOS)

    s_L_is_sessions = L_is["entry_date"].nunique()
    s_L_oos_sessions = L_oos["entry_date"].nunique()
    s_Z_is_sessions = Z_is["entry_date"].nunique()
    s_Z_oos_sessions = Z_oos["entry_date"].nunique()

    L_is_st = _stats(L_is, s_L_is_sessions);    L_oos_st = _stats(L_oos, s_L_oos_sessions)
    Z_is_st = _stats(Z_is, s_Z_is_sessions);    Z_oos_st = _stats(Z_oos, s_Z_oos_sessions)

    L_is_pc = _per_cell(L_is, s_L_is_sessions);   L_oos_pc = _per_cell(L_oos, s_L_oos_sessions)
    Z_is_pc = _per_cell(Z_is, s_Z_is_sessions);   Z_oos_pc = _per_cell(Z_oos, s_Z_oos_sessions)

    L_is_msl = _stats(L_is[L_is["cell"] != SL_CELL], s_L_is_sessions)
    L_oos_msl = _stats(L_oos[L_oos["cell"] != SL_CELL], s_L_oos_sessions)
    Z_is_msl = _stats(Z_is[Z_is["cell"] != SL_CELL], s_Z_is_sessions)
    Z_oos_msl = _stats(Z_oos[Z_oos["cell"] != SL_CELL], s_Z_oos_sessions)

    L_is_exits = L_is["exit_reason"].value_counts().to_dict()
    L_oos_exits = L_oos["exit_reason"].value_counts().to_dict()
    Z_is_exits = Z_is["exit_reason"].value_counts().to_dict()
    Z_oos_exits = Z_oos["exit_reason"].value_counts().to_dict()

    # Time-of-day split (before vs after 12:30 ET) on locked model only
    L_is_pre = _stats(L_is[L_is["before_1230"]], s_L_is_sessions)
    L_is_post = _stats(L_is[~L_is["before_1230"]], s_L_is_sessions)
    L_oos_pre = _stats(L_oos[L_oos["before_1230"]], s_L_oos_sessions)
    L_oos_post = _stats(L_oos[~L_oos["before_1230"]], s_L_oos_sessions)

    # IS→OOS Sharpe degradation
    def degrade(s_is, s_oos):
        if s_is is None or s_oos is None or s_is == 0:
            return None
        return (s_oos - s_is) / abs(s_is) * 100  # % change

    locked_degrade = degrade(L_is_st["sharpe"], L_oos_st["sharpe"])
    zach_degrade = degrade(Z_is_st["sharpe"], Z_oos_st["sharpe"])

    print("=" * 72)
    print("ZACH OMEN 2.0 vs LOCKED BUGFIXED BASELINE — head-to-head")
    print("=" * 72)
    print(f"\nIS metric            {'locked':>10s}  {'Zach':>10s}  {'Δ':>10s}")
    print(f"  N trades          {L_is_st['n']:>10d}  {Z_is_st['n']:>10d}  "
          f"{Z_is_st['n']-L_is_st['n']:>+10d}")
    print(f"  Win rate          {L_is_st['win_rate']*100:>9.2f}%  "
          f"{Z_is_st['win_rate']*100:>9.2f}%  "
          f"{(Z_is_st['win_rate']-L_is_st['win_rate'])*100:>+9.2f}pp")
    print(f"  Mean $            {L_is_st['mean']:>+10.2f}  {Z_is_st['mean']:>+10.2f}  "
          f"{Z_is_st['mean']-L_is_st['mean']:>+10.2f}")
    print(f"  Sum $             {L_is_st['sum']:>+10.0f}  {Z_is_st['sum']:>+10.0f}  "
          f"{Z_is_st['sum']-L_is_st['sum']:>+10.0f}")
    print(f"  Sharpe            {_fmt_sh(L_is_st['sharpe']):>10s}  "
          f"{_fmt_sh(Z_is_st['sharpe']):>10s}  "
          f"{Z_is_st['sharpe']-L_is_st['sharpe']:>+10.2f}")
    print(f"  Max DD $          {L_is_st['max_dd']:>+10.0f}  {Z_is_st['max_dd']:>+10.0f}  "
          f"{Z_is_st['max_dd']-L_is_st['max_dd']:>+10.0f}")
    print(f"  Mean bars_held    {L_is_st['mean_bars_held']:>10.2f}  "
          f"{Z_is_st['mean_bars_held']:>10.2f}")
    print(f"  Minus-SL Sharpe   {_fmt_sh(L_is_msl['sharpe']):>10s}  "
          f"{_fmt_sh(Z_is_msl['sharpe']):>10s}  "
          f"{Z_is_msl['sharpe']-L_is_msl['sharpe']:>+10.2f}")
    print(f"\nOOS metric           {'locked':>10s}  {'Zach':>10s}  {'Δ':>10s}")
    print(f"  N trades          {L_oos_st['n']:>10d}  {Z_oos_st['n']:>10d}  "
          f"{Z_oos_st['n']-L_oos_st['n']:>+10d}")
    print(f"  Win rate          {L_oos_st['win_rate']*100:>9.2f}%  "
          f"{Z_oos_st['win_rate']*100:>9.2f}%  "
          f"{(Z_oos_st['win_rate']-L_oos_st['win_rate'])*100:>+9.2f}pp")
    print(f"  Mean $            {L_oos_st['mean']:>+10.2f}  {Z_oos_st['mean']:>+10.2f}  "
          f"{Z_oos_st['mean']-L_oos_st['mean']:>+10.2f}")
    print(f"  Sum $             {L_oos_st['sum']:>+10.0f}  {Z_oos_st['sum']:>+10.0f}  "
          f"{Z_oos_st['sum']-L_oos_st['sum']:>+10.0f}")
    print(f"  Sharpe            {_fmt_sh(L_oos_st['sharpe']):>10s}  "
          f"{_fmt_sh(Z_oos_st['sharpe']):>10s}  "
          f"{Z_oos_st['sharpe']-L_oos_st['sharpe']:>+10.2f}")
    print(f"  Max DD $          {L_oos_st['max_dd']:>+10.0f}  {Z_oos_st['max_dd']:>+10.0f}  "
          f"{Z_oos_st['max_dd']-L_oos_st['max_dd']:>+10.0f}")
    print(f"  Mean bars_held    {L_oos_st['mean_bars_held']:>10.2f}  "
          f"{Z_oos_st['mean_bars_held']:>10.2f}")
    print(f"  Minus-SL Sharpe   {_fmt_sh(L_oos_msl['sharpe']):>10s}  "
          f"{_fmt_sh(Z_oos_msl['sharpe']):>10s}  "
          f"{Z_oos_msl['sharpe']-L_oos_msl['sharpe']:>+10.2f}")

    print(f"\nIS→OOS degradation:")
    print(f"  Locked: IS {_fmt_sh(L_is_st['sharpe'])} → OOS {_fmt_sh(L_oos_st['sharpe'])}  "
          f"= {locked_degrade:+.1f}%")
    print(f"  Zach  : IS {_fmt_sh(Z_is_st['sharpe'])} → OOS {_fmt_sh(Z_oos_st['sharpe'])}  "
          f"= {zach_degrade:+.1f}%")

    print(f"\nLocked time-of-day split (pre/post 12:30):")
    print(f"  IS  pre-12:30: n={L_is_pre['n']:>3d} Sh={_fmt_sh(L_is_pre['sharpe'])} "
          f"mean ${L_is_pre['mean']:>+7.2f} sum ${L_is_pre['sum']:>+8.0f}")
    print(f"  IS  post-12:30: n={L_is_post['n']:>3d} Sh={_fmt_sh(L_is_post['sharpe'])} "
          f"mean ${L_is_post['mean']:>+7.2f} sum ${L_is_post['sum']:>+8.0f}")
    print(f"  OOS pre-12:30: n={L_oos_pre['n']:>3d} Sh={_fmt_sh(L_oos_pre['sharpe'])} "
          f"mean ${L_oos_pre['mean']:>+7.2f} sum ${L_oos_pre['sum']:>+8.0f}")
    print(f"  OOS post-12:30: n={L_oos_post['n']:>3d} Sh={_fmt_sh(L_oos_post['sharpe'])} "
          f"mean ${L_oos_post['mean']:>+7.2f} sum ${L_oos_post['sum']:>+8.0f}")

    print(f"\nExit reasons:")
    for r in ("time", "stop", "target", "trail", "session_close"):
        print(f"  {r:<14s}  "
              f"locked_IS={L_is_exits.get(r,0):>4d}  locked_OOS={L_oos_exits.get(r,0):>4d}  "
              f"zach_IS={Z_is_exits.get(r,0):>4d}    zach_OOS={Z_oos_exits.get(r,0):>4d}")

    print("\nPer-cell IS:")
    for c in CELLS:
        Lp = L_is_pc[c]; Zp = Z_is_pc[c]
        print(f"  {c:<12s}  locked n={Lp['n']:>3d} Sh={_fmt_sh(Lp['sharpe']):>6s}  "
              f"zach n={Zp['n']:>3d} Sh={_fmt_sh(Zp['sharpe']):>6s}")
    print("\nPer-cell OOS:")
    for c in CELLS:
        Lp = L_oos_pc[c]; Zp = Z_oos_pc[c]
        print(f"  {c:<12s}  locked n={Lp['n']:>3d} Sh={_fmt_sh(Lp['sharpe']):>6s}  "
              f"zach n={Zp['n']:>3d} Sh={_fmt_sh(Zp['sharpe']):>6s}")

    md = _synthesize(
        L_is_st=L_is_st, L_oos_st=L_oos_st, Z_is_st=Z_is_st, Z_oos_st=Z_oos_st,
        L_is_pc=L_is_pc, L_oos_pc=L_oos_pc, Z_is_pc=Z_is_pc, Z_oos_pc=Z_oos_pc,
        L_is_msl=L_is_msl, L_oos_msl=L_oos_msl, Z_is_msl=Z_is_msl, Z_oos_msl=Z_oos_msl,
        L_is_exits=L_is_exits, L_oos_exits=L_oos_exits,
        Z_is_exits=Z_is_exits, Z_oos_exits=Z_oos_exits,
        L_is_pre=L_is_pre, L_is_post=L_is_post,
        L_oos_pre=L_oos_pre, L_oos_post=L_oos_post,
        locked_degrade=locked_degrade, zach_degrade=zach_degrade,
        s_L_is=s_L_is_sessions, s_L_oos=s_L_oos_sessions,
        s_Z_is=s_Z_is_sessions, s_Z_oos=s_Z_oos_sessions,
    )
    OUT_MD.write_text(md)
    print(f"\nSaved synthesis: {OUT_MD}")
    return 0


DISCLOSURE = """\
This is exploratory comparison of Zach's Omen 2.0 against the
honest bugfixed locked baseline on the same consumed IS/OOS corpus.
Both models use the same bugfixed infrastructure (features.py
session-boundary fix, backtest.py time-stop and overlap fixes).
Parameter differences are what's being compared. Results are
in-sample for both models — neither has been forward-tested on
clean data. No deployment decision should be made based on this
comparison alone.
"""


def _synthesize(**kw) -> str:
    L_is = kw["L_is_st"]; L_oos = kw["L_oos_st"]
    Z_is = kw["Z_is_st"]; Z_oos = kw["Z_oos_st"]
    L: list[str] = []
    L.append("# Zach Omen 2.0 vs locked bugfixed baseline — head-to-head\n")
    L.append("Branch: `analysis/zach-omen2-full-comparison-throwaway` "
             "(throwaway / archive only; never merges to main).")
    L.append(f"Generated: {datetime.now().isoformat(timespec='seconds')}\n")
    L.append("## 1. Disclosure\n")
    L.append(DISCLOSURE)
    L.append("")

    # Parameter table
    L.append("## 2. Parameter difference summary\n")
    L.append("| param | locked (bugfixed) | Zach Omen 2.0 |")
    L.append("|---|---|---|")
    L.append("| z_threshold | 1.8 | **2.0** |")
    L.append("| blackout_lunch | True | **False** |")
    L.append("| TRADE_START_TIME | n/a | **12:30 ET** |")
    L.append("| stop_atr_mult | 2.0 | **1.5** |")
    L.append("| target_atr_mult | 4.5 | **2.5** |")
    L.append("| trail_after_r | 0 | **1.0** (trailing ON) |")
    L.append("| time_stop_min | 25 | **30** |")
    L.append("| atr_window_bars | 14 | 14 (same) |")
    L.append("| feature_lookback_bars | 20 | 60 (informational) |")
    L.append("| bar_freq | 5min | 5min |")
    L.append("")
    L.append("Both models run on:")
    L.append("- Same IS window: 2025-12-30 → 2026-04-21")
    L.append("- Same OOS window: 2025-09-08 → 2025-12-23")
    L.append("- Same bugfixed infrastructure (commits c333405, c52a9ab on main)")
    L.append("")

    # Side-by-side
    L.append("## 3. Side-by-side performance\n")
    L.append("### IS (2025-12-30 → 2026-04-21)\n")
    L.append("| metric | locked | Zach | Δ |")
    L.append("|---|---:|---:|---:|")
    L.append(f"| N trades | {L_is['n']} | {Z_is['n']} | {Z_is['n']-L_is['n']:+d} |")
    L.append(f"| Win rate | {_fmt_wr(L_is['win_rate'])} | {_fmt_wr(Z_is['win_rate'])} | "
             f"{(Z_is['win_rate']-L_is['win_rate'])*100:+.1f} pp |")
    L.append(f"| Mean $ | ${L_is['mean']:+.2f} | ${Z_is['mean']:+.2f} | "
             f"${Z_is['mean']-L_is['mean']:+.2f} |")
    L.append(f"| Sum $ | ${L_is['sum']:+.0f} | ${Z_is['sum']:+.0f} | "
             f"${Z_is['sum']-L_is['sum']:+.0f} |")
    L.append(f"| **Sharpe** | **{_fmt_sh(L_is['sharpe'])}** | **{_fmt_sh(Z_is['sharpe'])}** | "
             f"**{Z_is['sharpe']-L_is['sharpe']:+.2f}** |")
    L.append(f"| Max DD $ | ${L_is['max_dd']:+.0f} | ${Z_is['max_dd']:+.0f} | "
             f"${Z_is['max_dd']-L_is['max_dd']:+.0f} |")
    L.append(f"| Mean bars_held | {L_is['mean_bars_held']:.2f} | "
             f"{Z_is['mean_bars_held']:.2f} | "
             f"{Z_is['mean_bars_held']-L_is['mean_bars_held']:+.2f} |")
    L.append(f"| Minus-SL Sharpe | {_fmt_sh(kw['L_is_msl']['sharpe'])} | "
             f"{_fmt_sh(kw['Z_is_msl']['sharpe'])} | "
             f"{(kw['Z_is_msl']['sharpe'] or 0)-(kw['L_is_msl']['sharpe'] or 0):+.2f} |")
    L.append("")
    L.append("### OOS (2025-09-08 → 2025-12-23)\n")
    L.append("| metric | locked | Zach | Δ |")
    L.append("|---|---:|---:|---:|")
    L.append(f"| N trades | {L_oos['n']} | {Z_oos['n']} | {Z_oos['n']-L_oos['n']:+d} |")
    L.append(f"| Win rate | {_fmt_wr(L_oos['win_rate'])} | {_fmt_wr(Z_oos['win_rate'])} | "
             f"{(Z_oos['win_rate']-L_oos['win_rate'])*100:+.1f} pp |")
    L.append(f"| Mean $ | ${L_oos['mean']:+.2f} | ${Z_oos['mean']:+.2f} | "
             f"${Z_oos['mean']-L_oos['mean']:+.2f} |")
    L.append(f"| Sum $ | ${L_oos['sum']:+.0f} | ${Z_oos['sum']:+.0f} | "
             f"${Z_oos['sum']-L_oos['sum']:+.0f} |")
    L.append(f"| **Sharpe** | **{_fmt_sh(L_oos['sharpe'])}** | **{_fmt_sh(Z_oos['sharpe'])}** | "
             f"**{Z_oos['sharpe']-L_oos['sharpe']:+.2f}** |")
    L.append(f"| Max DD $ | ${L_oos['max_dd']:+.0f} | ${Z_oos['max_dd']:+.0f} | "
             f"${Z_oos['max_dd']-L_oos['max_dd']:+.0f} |")
    L.append(f"| Mean bars_held | {L_oos['mean_bars_held']:.2f} | "
             f"{Z_oos['mean_bars_held']:.2f} | "
             f"{Z_oos['mean_bars_held']-L_oos['mean_bars_held']:+.2f} |")
    L.append(f"| Minus-SL Sharpe | {_fmt_sh(kw['L_oos_msl']['sharpe'])} | "
             f"{_fmt_sh(kw['Z_oos_msl']['sharpe'])} | "
             f"{(kw['Z_oos_msl']['sharpe'] or 0)-(kw['L_oos_msl']['sharpe'] or 0):+.2f} |")
    L.append("")

    # Diagnostics
    L.append("## 4. Key diagnostic findings\n")
    L.append("### (a) Does the 12:30 start time eliminate morning losing trades?\n")
    L.append("Time-of-day split on the **locked** model (Zach's model fires only after 12:30 by design):\n")
    L.append("| period | sample | n | Sharpe | mean $ | sum $ |")
    L.append("|---|---|---:|---:|---:|---:|")
    L_is_pre = kw["L_is_pre"]; L_is_post = kw["L_is_post"]
    L_oos_pre = kw["L_oos_pre"]; L_oos_post = kw["L_oos_post"]
    L.append(f"| pre-12:30 | IS | {L_is_pre['n']} | {_fmt_sh(L_is_pre['sharpe'])} | "
             f"${L_is_pre['mean']:+.2f} | ${L_is_pre['sum']:+.0f} |")
    L.append(f"| post-12:30 | IS | {L_is_post['n']} | {_fmt_sh(L_is_post['sharpe'])} | "
             f"${L_is_post['mean']:+.2f} | ${L_is_post['sum']:+.0f} |")
    L.append(f"| pre-12:30 | OOS | {L_oos_pre['n']} | {_fmt_sh(L_oos_pre['sharpe'])} | "
             f"${L_oos_pre['mean']:+.2f} | ${L_oos_pre['sum']:+.0f} |")
    L.append(f"| post-12:30 | OOS | {L_oos_post['n']} | {_fmt_sh(L_oos_post['sharpe'])} | "
             f"${L_oos_post['mean']:+.2f} | ${L_oos_post['sum']:+.0f} |")
    L.append("")
    pre_sum_total = L_is_pre['sum'] + L_oos_pre['sum']
    post_sum_total = L_is_post['sum'] + L_oos_post['sum']
    if pre_sum_total < 0 and post_sum_total > 0:
        L.append(f"**Locked model loses money on pre-12:30 trades** (total ${pre_sum_total:+.0f} ")
        L.append(f"across {L_is_pre['n']+L_oos_pre['n']} trades) and makes money on post-12:30 ")
        L.append(f"(total ${post_sum_total:+.0f}). Zach's 12:30 hard filter excludes these ")
        L.append("losing morning entries by construction.")
    else:
        L.append(f"Pre-12:30 trades total ${pre_sum_total:+.0f}; post-12:30 total ${post_sum_total:+.0f}. ")
        L.append("Zach's 12:30 filter excludes the pre-12:30 set entirely.")
    L.append("")

    L.append("### (b) Does SHORT_long still appear broken in Zach's model?\n")
    sl_o = kw["L_oos_pc"][SL_CELL]; sl_z = kw["Z_oos_pc"][SL_CELL]
    L.append(f"OOS SHORT_long: locked n={sl_o['n']} Sh={_fmt_sh(sl_o['sharpe'])}, "
             f"sum ${sl_o['sum']:+.0f}; Zach n={sl_z['n']} Sh={_fmt_sh(sl_z['sharpe'])}, "
             f"sum ${sl_z['sum']:+.0f}.")
    if (sl_z["sharpe"] is not None and sl_z["sharpe"] < 0
        and sl_o["sharpe"] is not None and sl_o["sharpe"] < 0):
        L.append("**Yes** — SHORT_long remains negative-Sharpe under both models. The ")
        L.append("12:30 filter and tighter exits don't fix the SHORT_long cell.")
    elif sl_z["sharpe"] is not None and sl_z["sharpe"] >= 0:
        L.append("**No** — under Zach's model, SHORT_long Sharpe is non-negative. The ")
        L.append("parameter changes (12:30 filter, trailing stop, tighter target) may ")
        L.append("address the SHORT_long problem incidentally.")
    L.append("")

    L.append("### (c) Does the trailing stop improve outcomes?\n")
    z_exits = kw["Z_is_exits"]
    n_trail_is = z_exits.get("trail", 0)
    n_trail_oos = kw["Z_oos_exits"].get("trail", 0)
    L.append(f"Trailing-stop exits in Zach's runs: IS={n_trail_is}, OOS={n_trail_oos}.")
    if n_trail_is + n_trail_oos == 0:
        L.append("Zero trailing-stop exits fired. Either (i) the trailing stop never armed ")
        L.append("(no trade ever reached +1R before being exited by another rule), or ")
        L.append("(ii) backtest.py logs ratcheted-stop exits as 'stop' rather than 'trail'. ")
        L.append("Check exit-reason taxonomy in backtest.py if attribution matters.")
    else:
        L.append("The trailing stop is active. Its effect is bundled into the aggregate ")
        L.append("Sharpe difference; isolating its contribution would require an A/B run ")
        L.append("with trail_after_r=0 holding everything else constant.")
    L.append("")

    L.append("### (d) Tighter target (2.5×ATR vs 4.5×ATR): win rate vs avg win tradeoff\n")
    L.append("| sample | locked win_rate | Zach win_rate | locked mean $ | Zach mean $ |")
    L.append("|---|---:|---:|---:|---:|")
    L.append(f"| IS  | {_fmt_wr(L_is['win_rate'])} | {_fmt_wr(Z_is['win_rate'])} | "
             f"${L_is['mean']:+.2f} | ${Z_is['mean']:+.2f} |")
    L.append(f"| OOS | {_fmt_wr(L_oos['win_rate'])} | {_fmt_wr(Z_oos['win_rate'])} | "
             f"${L_oos['mean']:+.2f} | ${Z_oos['mean']:+.2f} |")
    L.append("")
    if Z_is["win_rate"] > L_is["win_rate"] and Z_is["mean"] < L_is["mean"]:
        L.append("Tighter target produces higher win-rate but smaller average win (classic ")
        L.append("tradeoff). The Sharpe winner depends on whether the win-rate gain outweighs ")
        L.append("the smaller mean win.")
    L.append("")

    L.append("### (e) IS→OOS consistency\n")
    L.append(f"- **Locked**:  IS {_fmt_sh(L_is['sharpe'])} → OOS {_fmt_sh(L_oos['sharpe'])}  ")
    L.append(f"  = {kw['locked_degrade']:+.1f}% Sharpe degradation")
    L.append(f"- **Zach**: IS {_fmt_sh(Z_is['sharpe'])} → OOS {_fmt_sh(Z_oos['sharpe'])}  ")
    L.append(f"  = {kw['zach_degrade']:+.1f}% Sharpe degradation")
    L.append("")
    abs_locked = abs(kw["locked_degrade"]) if kw["locked_degrade"] is not None else 999
    abs_zach = abs(kw["zach_degrade"]) if kw["zach_degrade"] is not None else 999
    if abs_zach < abs_locked - 10:
        L.append(f"**Zach's model degrades less** by ~{abs_locked - abs_zach:.0f} pp on Sharpe. ")
        L.append("If this generalizes forward, the OMEN 2.0 architecture is more robust IS→OOS.")
    elif abs_zach > abs_locked + 10:
        L.append(f"**Locked baseline degrades less** by ~{abs_zach - abs_locked:.0f} pp. ")
        L.append("Zach's tighter parameters may be more overfit to the IS window.")
    else:
        L.append("Degradation is similar across both models.")
    L.append("")

    # Per-cell
    L.append("## 5. Per-cell breakdown comparison\n")
    L.append("### IS\n")
    L.append("| cell | locked N | locked Sh | Zach N | Zach Sh |")
    L.append("|---|---:|---:|---:|---:|")
    for c in CELLS:
        Lp = kw["L_is_pc"][c]; Zp = kw["Z_is_pc"][c]
        L.append(f"| {c} | {Lp['n']} | {_fmt_sh(Lp['sharpe'])} | "
                 f"{Zp['n']} | {_fmt_sh(Zp['sharpe'])} |")
    L.append("")
    L.append("### OOS\n")
    L.append("| cell | locked N | locked Sh | Zach N | Zach Sh |")
    L.append("|---|---:|---:|---:|---:|")
    for c in CELLS:
        Lp = kw["L_oos_pc"][c]; Zp = kw["Z_oos_pc"][c]
        L.append(f"| {c} | {Lp['n']} | {_fmt_sh(Lp['sharpe'])} | "
                 f"{Zp['n']} | {_fmt_sh(Zp['sharpe'])} |")
    L.append("")

    # Exit reasons
    L.append("## 6. Exit-reason distribution\n")
    L.append("| exit_reason | locked IS | Zach IS | locked OOS | Zach OOS |")
    L.append("|---|---:|---:|---:|---:|")
    for r in ("time", "stop", "target", "trail", "session_close"):
        L.append(f"| {r} | {kw['L_is_exits'].get(r,0)} | {kw['Z_is_exits'].get(r,0)} | "
                 f"{kw['L_oos_exits'].get(r,0)} | {kw['Z_oos_exits'].get(r,0)} |")
    L.append("")

    # IS→OOS comparison
    L.append("## 7. IS→OOS consistency comparison\n")
    L.append("| model | IS Sharpe | OOS Sharpe | Δ pts | % degradation |")
    L.append("|---|---:|---:|---:|---:|")
    L.append(f"| Locked (bugfixed) | {_fmt_sh(L_is['sharpe'])} | "
             f"{_fmt_sh(L_oos['sharpe'])} | "
             f"{L_oos['sharpe']-L_is['sharpe']:+.2f} | "
             f"{kw['locked_degrade']:+.1f}% |")
    L.append(f"| Zach Omen 2.0 | {_fmt_sh(Z_is['sharpe'])} | "
             f"{_fmt_sh(Z_oos['sharpe'])} | "
             f"{Z_oos['sharpe']-Z_is['sharpe']:+.2f} | "
             f"{kw['zach_degrade']:+.1f}% |")
    L.append("")

    # Honest interpretation
    L.append("## 8. Honest interpretation\n")
    z_oos = Z_oos["sharpe"]; l_oos = L_oos["sharpe"]
    if z_oos is None or l_oos is None:
        L.append("Could not compute Sharpe(s); inspect per-window stats.")
    elif z_oos > l_oos + 0.3:
        L.append(f"**Zach's OOS Sharpe ({_fmt_sh(z_oos)}) exceeds the locked baseline ")
        L.append(f"({_fmt_sh(l_oos)}) by {z_oos-l_oos:+.2f} points.** The architectural ")
        L.append("changes look better out of sample on this corpus. Worth forward-testing ")
        L.append("the OMEN 2.0 architecture on fresh sessions. **NOT a deployment authorization** ")
        L.append("— forward-test pre-reg on 30+ unconsumed sessions required.")
    elif z_oos > l_oos - 0.3:
        L.append(f"**Zach's OOS Sharpe ({_fmt_sh(z_oos)}) is roughly comparable to the ")
        L.append(f"locked baseline ({_fmt_sh(l_oos)}).** Different flavor of the same edge — ")
        L.append("no clear winner on these windows. Tradeoffs: tighter target / higher win-rate ")
        L.append("vs longer hold / wider profit potential. Neither dominates.")
    else:
        L.append(f"**Zach's OOS Sharpe ({_fmt_sh(z_oos)}) is worse than the locked baseline ")
        L.append(f"({_fmt_sh(l_oos)}).** Despite the architectural changes (12:30 filter, tighter ")
        L.append("exits, trailing stop), Zach's parameter set under-performs on the OOS window. ")
        L.append("Possible explanations: (a) tighter target clips winners more than it adds ")
        L.append("win-rate, (b) trailing stop ratchets to breakeven before the trade matures, ")
        L.append("(c) 12:30 filter loses some productive morning entries on this corpus.")
    L.append("")
    L.append("**IS→OOS consistency is more important than IS Sharpe alone.** If Zach's IS ")
    L.append("Sharpe is higher but degrades more severely OOS, that's a fitting-to-IS signal, ")
    L.append("not robustness.")
    L.append("")

    # Caveats
    L.append("## 9. Caveats (mandatory)\n")
    L.append("- Both models tested on the same consumed 160-session corpus. **In-sample** ")
    L.append("  for both — neither has any forward-test data point.")
    L.append("- Zach's parameters have UNKNOWN provenance with respect to this corpus. They ")
    L.append("  may have been derived from independent analysis (good) or tuned on this same ")
    L.append("  data (bad). Without provenance, OOS Sharpe is not clean validation.")
    L.append("- No forward-test validation exists for either model.")
    L.append("- Per-cell N under Zach's stricter parameters (z=2.0 + 12:30 filter) is smaller ")
    L.append("  than under locked. Individual cell Sharpes are noisier as a result.")
    L.append("- The OMEN-minus-SL hypothesis still hangs on the SHORT_long cell, which is ")
    L.append("  visible in both models. Whether 'minus-SL' is the right exclusion rule, or ")
    L.append("  whether the SHORT_long cell can be fixed structurally, remains open.")
    L.append("- A proper next step would be a pre-registered forward test on 30+ fresh ")
    L.append("  sessions, written BEFORE seeing more of this corpus's behavior. The locked ")
    L.append("  baseline and Zach's variant could both be evaluated against the same fresh ")
    L.append("  data.")
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
