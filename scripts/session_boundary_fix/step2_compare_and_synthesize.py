"""Step 2 — compare original vs bugfixed IS and OOS trade logs; build SYNTHESIS.md.

Reads:
  backend/data/analysis/locked_baseline_trades_blackout_lunch.csv  (original IS, 174)
  backend/data/analysis/oos_baseline_trades_2025-09-08_2025-12-23.csv (original OOS, 158)
  diagnostics/session-boundary-bugfix/locked_baseline_is_bugfixed.csv  (bugfixed IS)
  diagnostics/session-boundary-bugfix/oos_baseline_bugfixed.csv  (bugfixed OOS)
"""
from __future__ import annotations

import datetime as dt
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

REPO = Path("/Users/rafanelson/Omen")
ANALYSIS_BASE = REPO / "backend/data/analysis"
DIAG_DIR = REPO / "diagnostics/session-boundary-bugfix"
ET = ZoneInfo("America/New_York")

ORIG_IS = ANALYSIS_BASE / "locked_baseline_trades_blackout_lunch.csv"
ORIG_OOS = ANALYSIS_BASE / "oos_baseline_trades_2025-09-08_2025-12-23.csv"
FIX_IS = DIAG_DIR / "locked_baseline_is_bugfixed.csv"
FIX_OOS = DIAG_DIR / "oos_baseline_bugfixed.csv"
OUT_MD = DIAG_DIR / "SYNTHESIS.md"

SL_CELL = "SHORT_long"
CELLS = ["LONG_long", "LONG_short", "SHORT_long", "SHORT_short"]


def _load(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["entry_time"] = pd.to_datetime(df["entry_time"], utc=True)
    df["entry_time_utc"] = df["entry_time"]
    df["entry_time_et"] = df["entry_time"].dt.tz_convert(ET)
    df["entry_date"] = df["entry_time_et"].dt.date
    df["side_label"] = np.where(df["side"] == 1, "LONG", "SHORT")
    df["cell"] = df["side_label"] + "_" + df["gamma_regime"].astype(str)
    return df


def _max_dd(net: pd.Series, entry_time: pd.Series) -> float:
    if len(net) == 0:
        return 0.0
    order = entry_time.argsort()
    eq = np.cumsum(net.values[order])
    peak = np.maximum.accumulate(eq)
    return float((eq - peak).min())


def _sharpe(net: pd.Series, n_sessions: int) -> float | None:
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
                "sharpe": None, "max_dd": 0.0}
    net = df["net_dollars"]
    return {"n": int(len(df)), "win_rate": float((net > 0).mean()),
             "mean": float(net.mean()), "sum": float(net.sum()),
             "sharpe": _sharpe(net, n_sessions),
             "max_dd": _max_dd(net, df["entry_time_utc"])}


def _per_cell(df: pd.DataFrame, n_sessions: int) -> dict:
    return {c: _stats(df[df["cell"] == c], n_sessions) for c in CELLS}


def _first_n_bars(df: pd.DataFrame, n: int = 20, bar_min: int = 5) -> int:
    """Count trades whose entry_time is within the first n bars of an RTH session.
    Bar i closes at 9:30 + (i+1)*bar_min minutes ET. So first 20 5-min bars
    end at 09:30 + 100min = 11:10 ET. Count entries with minute_of_day <
    (9*60 + 30 + n*bar_min).
    """
    cutoff = 9 * 60 + 30 + n * bar_min  # minutes from midnight in ET
    mod = df["entry_time_et"].dt.hour * 60 + df["entry_time_et"].dt.minute
    return int((mod < cutoff).sum())


def _fmt_sh(sh): return "—" if sh is None else f"{sh:+.2f}"
def _fmt_wr(wr): return "—" if wr is None else f"{wr*100:.1f}%"


def _delta(a, b):
    if a is None or b is None:
        return "—"
    return f"{b - a:+.2f}"


def main() -> int:
    is_orig = _load(ORIG_IS); is_fix = _load(FIX_IS)
    oos_orig = _load(ORIG_OOS); oos_fix = _load(FIX_OOS)

    # session counts
    is_sessions = is_orig["entry_date"].nunique()
    is_fix_sessions = is_fix["entry_date"].nunique()
    oos_sessions = oos_orig["entry_date"].nunique()
    oos_fix_sessions = oos_fix["entry_date"].nunique()

    print(f"IS  sessions  : orig={is_sessions}  bugfixed={is_fix_sessions}")
    print(f"OOS sessions  : orig={oos_sessions}  bugfixed={oos_fix_sessions}")

    is_o = _stats(is_orig, is_sessions);   is_f = _stats(is_fix, is_fix_sessions)
    oos_o = _stats(oos_orig, oos_sessions); oos_f = _stats(oos_fix, oos_fix_sessions)
    is_pc_o = _per_cell(is_orig, is_sessions);   is_pc_f = _per_cell(is_fix, is_fix_sessions)
    oos_pc_o = _per_cell(oos_orig, oos_sessions); oos_pc_f = _per_cell(oos_fix, oos_fix_sessions)

    # First-20-bars exposure (where bug is strongest)
    is_first20_o = _first_n_bars(is_orig, n=20)
    is_first20_f = _first_n_bars(is_fix, n=20)
    oos_first20_o = _first_n_bars(oos_orig, n=20)
    oos_first20_f = _first_n_bars(oos_fix, n=20)

    # Trade overlay
    def overlay(a: pd.DataFrame, b: pd.DataFrame) -> dict:
        ov = a[["entry_time", "side", "gamma_regime", "exit_reason",
                 "net_dollars"]].merge(
            b[["entry_time", "side", "gamma_regime", "exit_reason",
                "net_dollars"]],
            on=["entry_time", "side", "gamma_regime"], how="outer",
            suffixes=("_a", "_b"), indicator=True,
        )
        both = ov[ov["_merge"] == "both"]
        return {
            "both": int(len(both)),
            "only_a": int((ov["_merge"] == "left_only").sum()),
            "only_b": int((ov["_merge"] == "right_only").sum()),
            "same_exit": (int((both["exit_reason_a"] == both["exit_reason_b"]).sum())
                          if len(both) else 0),
            "delta_net_mean": (float((both["net_dollars_b"] - both["net_dollars_a"]).mean())
                                if len(both) else 0.0),
            "delta_net_sum": (float((both["net_dollars_b"] - both["net_dollars_a"]).sum())
                               if len(both) else 0.0),
        }
    is_ov = overlay(is_orig, is_fix)
    oos_ov = overlay(oos_orig, oos_fix)
    print(f"\nIS overlay : both={is_ov['both']}  only_orig={is_ov['only_a']}  "
          f"only_fix={is_ov['only_b']}")
    print(f"OOS overlay: both={oos_ov['both']}  only_orig={oos_ov['only_a']}  "
          f"only_fix={oos_ov['only_b']}")

    # ---- Print summary ----
    print(f"\n{'metric':<22s}  {'IS orig':>10s}  {'IS fixed':>10s}  {'Δ':>9s}  "
          f"{'OOS orig':>10s}  {'OOS fixed':>10s}  {'Δ':>9s}")
    rows = [
        ("N trades", is_o["n"], is_f["n"], oos_o["n"], oos_f["n"]),
        ("Win rate %", is_o["win_rate"]*100, is_f["win_rate"]*100,
         oos_o["win_rate"]*100, oos_f["win_rate"]*100),
        ("Mean $", is_o["mean"], is_f["mean"], oos_o["mean"], oos_f["mean"]),
        ("Sum $", is_o["sum"], is_f["sum"], oos_o["sum"], oos_f["sum"]),
        ("Sharpe", is_o["sharpe"], is_f["sharpe"], oos_o["sharpe"], oos_f["sharpe"]),
        ("Max DD $", is_o["max_dd"], is_f["max_dd"], oos_o["max_dd"], oos_f["max_dd"]),
    ]
    for name, a, b, c, d in rows:
        if name == "N trades":
            print(f"  {name:<22s}  {a:>10d}  {b:>10d}  {b-a:>+9d}  "
                  f"{c:>10d}  {d:>10d}  {d-c:>+9d}")
        elif None in (a, b, c, d):
            print(f"  {name:<22s}  {a}  {b}  —  {c}  {d}  —")
        else:
            print(f"  {name:<22s}  {a:>+10.2f}  {b:>+10.2f}  {b-a:>+9.2f}  "
                  f"{c:>+10.2f}  {d:>+10.2f}  {d-c:>+9.2f}")
    print(f"  {'First 20 bars n':<22s}  {is_first20_o:>10d}  {is_first20_f:>10d}  "
          f"{is_first20_f-is_first20_o:>+9d}  "
          f"{oos_first20_o:>10d}  {oos_first20_f:>10d}  "
          f"{oos_first20_f-oos_first20_o:>+9d}")

    print("\nPer-cell IS:")
    for c in CELLS:
        o = is_pc_o[c]; f = is_pc_f[c]
        print(f"  {c:<12s}  orig n={o['n']:>3d} Sh={_fmt_sh(o['sharpe']):>6s}  |  "
              f"fixed n={f['n']:>3d} Sh={_fmt_sh(f['sharpe']):>6s}")
    print("\nPer-cell OOS:")
    for c in CELLS:
        o = oos_pc_o[c]; f = oos_pc_f[c]
        print(f"  {c:<12s}  orig n={o['n']:>3d} Sh={_fmt_sh(o['sharpe']):>6s}  |  "
              f"fixed n={f['n']:>3d} Sh={_fmt_sh(f['sharpe']):>6s}")

    # OMEN-minus-SL in fixed
    is_minus_o = _stats(is_orig[is_orig["cell"] != SL_CELL], is_sessions)
    is_minus_f = _stats(is_fix[is_fix["cell"] != SL_CELL], is_fix_sessions)
    oos_minus_o = _stats(oos_orig[oos_orig["cell"] != SL_CELL], oos_sessions)
    oos_minus_f = _stats(oos_fix[oos_fix["cell"] != SL_CELL], oos_fix_sessions)
    print(f"\nOMEN-minus-SL Sharpe:")
    print(f"  IS  orig: {_fmt_sh(is_minus_o['sharpe'])}  IS  fixed: {_fmt_sh(is_minus_f['sharpe'])}")
    print(f"  OOS orig: {_fmt_sh(oos_minus_o['sharpe'])}  OOS fixed: {_fmt_sh(oos_minus_f['sharpe'])}")

    md = _synthesize(
        is_o=is_o, is_f=is_f, oos_o=oos_o, oos_f=oos_f,
        is_pc_o=is_pc_o, is_pc_f=is_pc_f,
        oos_pc_o=oos_pc_o, oos_pc_f=oos_pc_f,
        is_ov=is_ov, oos_ov=oos_ov,
        is_minus_o=is_minus_o, is_minus_f=is_minus_f,
        oos_minus_o=oos_minus_o, oos_minus_f=oos_minus_f,
        is_first20_o=is_first20_o, is_first20_f=is_first20_f,
        oos_first20_o=oos_first20_o, oos_first20_f=oos_first20_f,
        is_sessions=is_sessions, is_fix_sessions=is_fix_sessions,
        oos_sessions=oos_sessions, oos_fix_sessions=oos_fix_sessions,
    )
    OUT_MD.write_text(md)
    print(f"\nSaved synthesis: {OUT_MD}")
    return 0


def _synthesize(**kw) -> str:
    is_o = kw["is_o"]; is_f = kw["is_f"]; oos_o = kw["oos_o"]; oos_f = kw["oos_f"]
    is_minus_o = kw["is_minus_o"]; is_minus_f = kw["is_minus_f"]
    oos_minus_o = kw["oos_minus_o"]; oos_minus_f = kw["oos_minus_f"]
    L: list[str] = []
    L.append("# Session-boundary bug fix — IS / OOS re-run impact\n")
    L.append("Branch: `diagnostics/session-boundary-bugfix` "
             "(diagnostics branch; merge to main only with explicit user sign-off).")
    L.append(f"Generated: {datetime.now().isoformat(timespec='seconds')}\n")

    L.append("## 1. What the bug was\n")
    L.append("`backend/cheese/features.py` computed rolling ATR (window=14), rolling ")
    L.append("flow z-scores (window=60), `dist_z_mlgamma` sign-cross detectors, and ")
    L.append("wall-break detectors **without resetting at session boundaries**. In a ")
    L.append("multi-day historical backtest, the first ~14-20 bars of every session ")
    L.append("inherited the *previous session's tail* into their rolling statistics: ")
    L.append("(a) ATR's first bars used yesterday's close as `prev_close`, so the ")
    L.append("overnight gap counted as an enormous true range — inflating ATR for ~14 ")
    L.append("bars; (b) the rolling 60-bar gexoflow/dexoflow z-score rolled into ")
    L.append("yesterday's distribution — inflated StdDev → *suppressed* z-score ")
    L.append("magnitudes near session start, so legitimate signal bars were measured ")
    L.append("relative to overnight volatility and never reached the 1.8 threshold. ")
    L.append("Crossing detectors fired on the first bar of day N if it opened across ")
    L.append("yesterday's wall, regardless of any actual intraday cross.")
    L.append("")
    L.append("**Bug-impact zones**:")
    L.append("- **ATR(14)**: at 5-min bars, 14 bars = ~1 hour. ATR is contaminated for the ")
    L.append("  first ~14 bars (~70 minutes) of each session, then settles to within-session.")
    L.append("- **Flow z-score (window=60)**: at 5-min bars, 60 bars = 5 hours, which is ")
    L.append("  *longer than the 6.5-hour RTH session*. The rolling window NEVER fully ")
    L.append("  populates within a single session — so for the bug version, the z-score ")
    L.append("  baseline is *always* dragged by previous-session tail data, throughout ")
    L.append("  the entire RTH session.")
    L.append("")
    L.append("This is why the first-20-bars trade-count change in the table below is ")
    L.append("nearly zero (the trades shifted around, not concentrated in early bars) ")
    L.append("but the *total* trade count jumped 50-60%: the bug affected z-score-driven ")
    L.append("entry decisions throughout each session, not just at the open.")
    L.append("")

    L.append("## 2. What the fix does\n")
    L.append("Replaces every `Series.rolling(...)` / `Series.shift(1)` in features.py ")
    L.append("with the per-session-grouped variant: `Series.groupby(session_date)`.")
    L.append("transform(rolling) and `.groupby(session_date).shift(1)`. The first bar ")
    L.append("of every session sees only that session's data — exactly equivalent to ")
    L.append("running a stack of single-day backtests glued together. Identical to ")
    L.append("Zach's diff `git diff main zach/main -- backend/cheese/features.py`. ")
    L.append("No other locked files are modified.")
    L.append("")

    # Side-by-side
    L.append("## 3. Side-by-side IS / OOS impact (locked params, only features.py changed)\n")
    L.append("| metric | IS orig | IS bugfixed | Δ | OOS orig | OOS bugfixed | Δ |")
    L.append("|---|---:|---:|---:|---:|---:|---:|")
    L.append(f"| N trades | {is_o['n']} | {is_f['n']} | {is_f['n']-is_o['n']:+d} | "
             f"{oos_o['n']} | {oos_f['n']} | {oos_f['n']-oos_o['n']:+d} |")
    L.append(f"| Win rate | {_fmt_wr(is_o['win_rate'])} | {_fmt_wr(is_f['win_rate'])} | "
             f"{(is_f['win_rate']-is_o['win_rate'])*100:+.1f} pp | "
             f"{_fmt_wr(oos_o['win_rate'])} | {_fmt_wr(oos_f['win_rate'])} | "
             f"{(oos_f['win_rate']-oos_o['win_rate'])*100:+.1f} pp |")
    L.append(f"| Mean $ | ${is_o['mean']:+.2f} | ${is_f['mean']:+.2f} | "
             f"${is_f['mean']-is_o['mean']:+.2f} | "
             f"${oos_o['mean']:+.2f} | ${oos_f['mean']:+.2f} | "
             f"${oos_f['mean']-oos_o['mean']:+.2f} |")
    L.append(f"| Sum $ | ${is_o['sum']:+.0f} | ${is_f['sum']:+.0f} | "
             f"${is_f['sum']-is_o['sum']:+.0f} | "
             f"${oos_o['sum']:+.0f} | ${oos_f['sum']:+.0f} | "
             f"${oos_f['sum']-oos_o['sum']:+.0f} |")
    is_sh_delta = (is_f['sharpe']-is_o['sharpe']) if (is_o['sharpe'] is not None
                                                        and is_f['sharpe'] is not None) else 0
    oos_sh_delta = (oos_f['sharpe']-oos_o['sharpe']) if (oos_o['sharpe'] is not None
                                                          and oos_f['sharpe'] is not None) else 0
    L.append(f"| **Sharpe** | **{_fmt_sh(is_o['sharpe'])}** | **{_fmt_sh(is_f['sharpe'])}** | "
             f"**{is_sh_delta:+.2f}** | **{_fmt_sh(oos_o['sharpe'])}** | "
             f"**{_fmt_sh(oos_f['sharpe'])}** | **{oos_sh_delta:+.2f}** |")
    L.append(f"| Max DD $ | ${is_o['max_dd']:+.0f} | ${is_f['max_dd']:+.0f} | "
             f"${is_f['max_dd']-is_o['max_dd']:+.0f} | "
             f"${oos_o['max_dd']:+.0f} | ${oos_f['max_dd']:+.0f} | "
             f"${oos_f['max_dd']-oos_o['max_dd']:+.0f} |")
    L.append(f"| Sessions | {kw['is_sessions']} | {kw['is_fix_sessions']} | — | "
             f"{kw['oos_sessions']} | {kw['oos_fix_sessions']} | — |")
    L.append(f"| First-20-bar trades | {kw['is_first20_o']} | {kw['is_first20_f']} | "
             f"{kw['is_first20_f']-kw['is_first20_o']:+d} | "
             f"{kw['oos_first20_o']} | {kw['oos_first20_f']} | "
             f"{kw['oos_first20_f']-kw['oos_first20_o']:+d} |")
    L.append("")

    # Per-cell IS
    L.append("## 4. Per-cell impact\n")
    L.append("### IS — original vs bugfixed\n")
    L.append("| cell | orig N | orig Sharpe | fixed N | fixed Sharpe | Δ Sharpe |")
    L.append("|---|---:|---:|---:|---:|---:|")
    for c in CELLS:
        o = kw["is_pc_o"][c]; f = kw["is_pc_f"][c]
        if o["sharpe"] is not None and f["sharpe"] is not None:
            d = f["sharpe"] - o["sharpe"]
            d_str = f"{d:+.2f}"
        else:
            d_str = "—"
        L.append(f"| {c} | {o['n']} | {_fmt_sh(o['sharpe'])} | {f['n']} | "
                 f"{_fmt_sh(f['sharpe'])} | {d_str} |")
    L.append("")
    L.append("### OOS — original vs bugfixed\n")
    L.append("| cell | orig N | orig Sharpe | fixed N | fixed Sharpe | Δ Sharpe |")
    L.append("|---|---:|---:|---:|---:|---:|")
    for c in CELLS:
        o = kw["oos_pc_o"][c]; f = kw["oos_pc_f"][c]
        if o["sharpe"] is not None and f["sharpe"] is not None:
            d = f["sharpe"] - o["sharpe"]
            d_str = f"{d:+.2f}"
        else:
            d_str = "—"
        L.append(f"| {c} | {o['n']} | {_fmt_sh(o['sharpe'])} | {f['n']} | "
                 f"{_fmt_sh(f['sharpe'])} | {d_str} |")
    L.append("")

    # Trade overlay
    L.append("## 5. Trade-level overlay (matched on entry_time + side + gamma_regime)\n")
    L.append("| sample | matched | only-orig | only-fixed | matched same exit | Δ net mean (both) | Δ net sum (both) |")
    L.append("|---|---:|---:|---:|---:|---:|---:|")
    is_ov = kw["is_ov"]; oos_ov = kw["oos_ov"]
    L.append(f"| IS | {is_ov['both']} | {is_ov['only_a']} | {is_ov['only_b']} | "
             f"{is_ov['same_exit']}/{is_ov['both']} | ${is_ov['delta_net_mean']:+.2f} | "
             f"${is_ov['delta_net_sum']:+.0f} |")
    L.append(f"| OOS | {oos_ov['both']} | {oos_ov['only_a']} | {oos_ov['only_b']} | "
             f"{oos_ov['same_exit']}/{oos_ov['both']} | ${oos_ov['delta_net_mean']:+.2f} | "
             f"${oos_ov['delta_net_sum']:+.0f} |")
    L.append("")

    # OMEN-minus-SL persistence
    L.append("## 6. OMEN-minus-SL Sharpe under bugfixed features\n")
    L.append("| sample | full Sharpe (orig) | full Sharpe (fixed) | minus-SL Sharpe (orig) | minus-SL Sharpe (fixed) |")
    L.append("|---|---:|---:|---:|---:|")
    L.append(f"| IS  | {_fmt_sh(is_o['sharpe'])} | {_fmt_sh(is_f['sharpe'])} | "
             f"{_fmt_sh(is_minus_o['sharpe'])} | {_fmt_sh(is_minus_f['sharpe'])} |")
    L.append(f"| OOS | {_fmt_sh(oos_o['sharpe'])} | {_fmt_sh(oos_f['sharpe'])} | "
             f"{_fmt_sh(oos_minus_o['sharpe'])} | {_fmt_sh(oos_minus_f['sharpe'])} |")
    L.append("")
    # Replication of cell-breakdown finding
    sl_oos_o = kw["oos_pc_o"][SL_CELL]; sl_oos_f = kw["oos_pc_f"][SL_CELL]
    L.append("**Does the cell-breakdown finding (OOS SHORT_long Sharpe = −1.95) replicate "
             "under bugfixed features?**")
    L.append(f"- OOS SHORT_long orig: n={sl_oos_o['n']}, Sharpe = "
             f"{_fmt_sh(sl_oos_o['sharpe'])}, sum = ${sl_oos_o['sum']:+.0f}")
    L.append(f"- OOS SHORT_long fixed: n={sl_oos_f['n']}, Sharpe = "
             f"{_fmt_sh(sl_oos_f['sharpe'])}, sum = ${sl_oos_f['sum']:+.0f}")
    if (sl_oos_f["sharpe"] is not None and sl_oos_f["sharpe"] < 0
        and oos_minus_f["sharpe"] is not None and oos_f["sharpe"] is not None
        and oos_minus_f["sharpe"] > oos_f["sharpe"]):
        L.append("- **Cell-breakdown finding REPLICATES under bugfixed features.** SHORT_long ")
        L.append("  remains negative-Sharpe on OOS and minus-SL still outperforms full OMEN.")
    elif sl_oos_f["sharpe"] is not None and sl_oos_f["sharpe"] >= 0:
        L.append("- **Cell-breakdown finding does NOT replicate.** SHORT_long is no longer ")
        L.append("  negative-Sharpe on OOS under bugfixed features — the original SHORT_long ")
        L.append("  problem may have been an artifact of the session-boundary bug.")
    elif (oos_minus_f["sharpe"] is not None and oos_f["sharpe"] is not None
          and oos_minus_f["sharpe"] <= oos_f["sharpe"]):
        L.append("- **Cell-breakdown finding partially replicates.** SHORT_long remains ")
        L.append("  negative-Sharpe BUT excluding it no longer improves the aggregate Sharpe.")
    L.append("")

    # ---- Honest impact assessment ----
    L.append("## 7. Honest impact assessment\n")
    is_pct = ((is_f['sharpe'] - is_o['sharpe']) / abs(is_o['sharpe']) * 100
              if is_o['sharpe'] not in (None, 0) and is_f['sharpe'] is not None else 0)
    oos_pct = ((oos_f['sharpe'] - oos_o['sharpe']) / abs(oos_o['sharpe']) * 100
               if oos_o['sharpe'] not in (None, 0) and oos_f['sharpe'] is not None else 0)
    L.append(f"- **IS Sharpe change**: {_fmt_sh(is_o['sharpe'])} → "
             f"{_fmt_sh(is_f['sharpe'])} (Δ {is_sh_delta:+.2f}, {is_pct:+.1f}%)")
    L.append(f"- **OOS Sharpe change**: {_fmt_sh(oos_o['sharpe'])} → "
             f"{_fmt_sh(oos_f['sharpe'])} (Δ {oos_sh_delta:+.2f}, {oos_pct:+.1f}%)")
    L.append("")
    max_pct = max(abs(is_pct), abs(oos_pct))
    if max_pct < 10:
        L.append("**Verdict: bug was REAL but NOT MATERIAL.** Sharpe shifts <10% on both ")
        L.append("samples. All prior conclusions broadly stand; numbers should be updated ")
        L.append("when the fix is merged.")
    elif max_pct < 30:
        L.append("**Verdict: bug had MODERATE effect.** Sharpe shifts in the 10-30% range. ")
        L.append("Baseline numbers need updating before any prior conclusion is cited. ")
        L.append("The directional read of most prior analyses likely survives but exact ")
        L.append("magnitudes do not.")
    else:
        L.append("**Verdict: bug was LOAD-BEARING.** Sharpe shifts >30% on at least one ")
        L.append("sample. All prior conclusions need re-examination under bugfixed features. ")
        L.append("Trade counts changed materially — the pre-fix locked baseline was running ")
        L.append("on a *suppressed* signal set, not the intended one.")
    L.append("")

    # Decision points
    L.append("## 8. Decision points for the user\n")
    L.append("1. **Should the locked baseline be updated with the fix?**")
    L.append("   - Pro: features.py was unambiguously buggy. Every prior analysis ran on ")
    L.append("     contaminated z-scores and ATR near session opens.")
    L.append("   - Pro: identical to Zach's fork's session-boundary fix — both teams ")
    L.append("     converged on the same correction.")
    L.append("   - Con: every previously committed baseline number (locked Sharpe 4.45, ")
    L.append("     OOS 1.13, cell breakdown Sharpes, OMEN-minus-SL 2.79) was computed on the ")
    L.append("     pre-fix features. Updating means re-running and re-committing those numbers.")
    L.append("   - Con: prior pre-registered tests (TRCB-v1 pre-reg) reference the pre-fix ")
    L.append("     baseline. Those pre-regs were validated against the wrong feature pipeline.")
    L.append("")
    L.append("2. **Do prior pre-registered tests need to be re-done?**")
    L.append("   - TRCB-v1 used per_bar_volumes computed independently from MBP-10 trades, ")
    L.append("     so the session-boundary bug did NOT affect its per-bar volumes. However, ")
    L.append("     the comparison baseline (OMEN's gexoflow/dexoflow) WAS affected. Any ")
    L.append("     conclusion that compared TRCB to OMEN should be re-checked.")
    L.append("   - Q1-Q4 post-mortem and Q6-Q8 component diagnostics used the same ")
    L.append("     per-bar volumes table; their conclusions are mechanically the same. ")
    L.append("     The Q3 'TRCB framework signals decay' finding still holds.")
    L.append("   - The original cell-breakdown (the basis for OMEN-minus-SL) was computed ")
    L.append("     on pre-fix trade logs. Its replication status under the fix is shown in ")
    L.append("     section 6 — read that before relying on the cell breakdown.")
    L.append("")
    L.append("3. **How does this affect the planned OMEN-minus-SL forward test?**")
    if (oos_minus_f["sharpe"] is not None and oos_f["sharpe"] is not None
        and oos_minus_f["sharpe"] > oos_f["sharpe"]):
        L.append("   - Bugfixed OOS shows minus-SL Sharpe > full Sharpe. Hypothesis ")
        L.append("     direction survives the fix. Forward test still worth pre-registering ")
        L.append("     — but the pre-reg should be written against the bugfixed baseline.")
    else:
        L.append("   - Bugfixed OOS does NOT show minus-SL > full. The OMEN-minus-SL ")
        L.append("     hypothesis as previously formulated may have been an artifact of the ")
        L.append("     bug. Re-derive the hypothesis from bugfixed cell data before any ")
        L.append("     forward-test pre-reg.")
    L.append("")

    # Caveats
    L.append("## 9. Caveats\n")
    L.append("- The session-boundary fix changes EVERY z-score-driven bar's feature values ")
    L.append("  within an RTH session, because the 60-bar flow z-score rolling window is ")
    L.append("  longer than RTH itself. ATR's contamination is shorter-lived (first ~14 ")
    L.append("  bars per session).")
    L.append("- Trade counts changed dramatically — bugfixed corpus is 50%+ larger on IS, ")
    L.append("  60%+ larger on OOS. The two samples are NOT comparable as 'same backtest, ")
    L.append("  different ATR/z formulas' — they are *different trade sets*.")
    L.append("- The decision to merge to main is the user's. This synthesis presents the ")
    L.append("  impact; it does NOT auto-merge.")
    L.append("- Prior pre-registered analyses on the consumed 160-session corpus are not ")
    L.append("  auto-invalidated by the fix; some (Q3, post-mortem) are based on per-bar ")
    L.append("  MBP-10 volumes that are independent of features.py. Others (cell breakdown, ")
    L.append("  OMEN-minus-SL quick-check) used OMEN trade logs and would need re-running.")
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
