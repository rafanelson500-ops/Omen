"""Step 2 (ZACH MAY) — synthesize the three-way comparison report.

THROWAWAY. Compares fresh-session results across three parameter sets on
the same 8-session window:
  - locked z=1.8, target=4.5, time=25, ATR=14  (original quick-check)
  - locked z=1.8, target=4.5, time=25, ATR=20  (ATR sensitivity variant)
  - Zach May z=2.0, target=5.0, time=35, ATR=14 (this run)

NOT a basis for parameter switching. See DISCLOSURE for full caveats.
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
ANALYSIS_DIR = REPO / "analysis/omen-minus-sl-quickcheck"
ET = ZoneInfo("America/New_York")

LOCKED14_CSV = ANALYSIS_DIR / "fresh_session_trades_raw.csv"
LOCKED20_CSV = ANALYSIS_DIR / "fresh_session_trades_atr20_raw.csv"
ZACH_CSV     = ANALYSIS_DIR / "fresh_trades_zach_may.csv"
ZACH_MINUS_SL_CSV = ANALYSIS_DIR / "fresh_trades_zach_may_minus_sl.csv"
OUT_MD       = ANALYSIS_DIR / "SYNTHESIS_zach_may.md"

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


def _max_drawdown(net: pd.Series, entry_time: pd.Series) -> float:
    if len(net) == 0:
        return 0.0
    order = entry_time.argsort()
    eq = np.cumsum(net.values[order])
    peak = np.maximum.accumulate(eq)
    return float((eq - peak).min())


def _sharpe(net: pd.Series, n_sessions: int, min_n: int = 10) -> float | None:
    n = len(net)
    if n < min_n or n_sessions <= 0:
        return None
    tpd = n / n_sessions
    if tpd <= 0:
        return None
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
             "max_dd": _max_drawdown(net, df["entry_time_utc"])}


def _fmt_sh(sh): return "—" if sh is None else f"{sh:+.2f}"
def _fmt_wr(wr): return "—" if wr is None else f"{wr*100:.1f}%"


ZACH_DISCLOSURE = """\
## DISCLOSURE — provenance unknown, sample meaningless

This script applies an alternative parameter set sourced from a third-party
spreadsheet (Zach's monthly params) to the same 8-9 fresh OMEN sessions
used in the OMEN-minus-SL quick-check.

Provenance of alternative parameters: UNKNOWN. The user has not verified
whether these parameters come from a pre-registered adaptive framework,
mechanistic derivation, or monthly performance tuning. Without provenance,
any result here is uninterpretable as evidence about which parameter set
"works better."

Sample size: ~18 trades. Statistically meaningless for parameter comparison.

This test does NOT authorize switching the OMEN locked baseline. The user
has acknowledged that no parameter change will be made based on this result.
"""


def main() -> int:
    locked14 = _load(LOCKED14_CSV)
    locked20 = _load(LOCKED20_CSV)
    zach     = _load(ZACH_CSV)

    n_sessions = locked14["entry_date"].nunique()
    print(f"Sessions: {n_sessions}")

    # Aggregate stats
    s_l14_full   = _stats(locked14, n_sessions)
    s_l14_minus  = _stats(locked14[locked14["cell"] != SL_CELL], n_sessions)
    s_l20_full   = _stats(locked20, n_sessions)
    s_l20_minus  = _stats(locked20[locked20["cell"] != SL_CELL], n_sessions)
    s_z_full     = _stats(zach, n_sessions)
    zach_minus_df = zach[zach["cell"] != SL_CELL]
    s_z_minus    = _stats(zach_minus_df, n_sessions)

    # Save Zach minus-SL CSV
    zach_minus_df.to_csv(ZACH_MINUS_SL_CSV, index=False)
    print(f"Saved: {ZACH_MINUS_SL_CSV} ({len(zach_minus_df)} trades)")

    # Per-cell
    def per_cell(df):
        return {c: _stats(df[df["cell"] == c], n_sessions) for c in CELLS}
    pc14 = per_cell(locked14); pc20 = per_cell(locked20); pcz = per_cell(zach)

    # Trade-level overlay (entry_time matching) between locked14 and Zach
    overlay = locked14[["entry_time", "side", "gamma_regime", "exit_reason",
                         "bars_held", "net_dollars"]].merge(
        zach[["entry_time", "side", "gamma_regime", "exit_reason",
               "bars_held", "net_dollars"]],
        on=["entry_time", "side", "gamma_regime"], how="outer",
        suffixes=("_l14", "_z"), indicator=True,
    )
    only_locked = int((overlay["_merge"] == "left_only").sum())
    only_zach   = int((overlay["_merge"] == "right_only").sum())
    both        = int((overlay["_merge"] == "both").sum())
    print(f"\nTrade overlay (locked-14 vs Zach):")
    print(f"  trades in both    : {both}")
    print(f"  only in locked-14 : {only_locked}")
    print(f"  only in Zach      : {only_zach}")

    # Exit reason distribution
    exit_dists = {
        "locked_14": locked14["exit_reason"].value_counts().to_dict(),
        "locked_20": locked20["exit_reason"].value_counts().to_dict(),
        "zach_may":  zach["exit_reason"].value_counts().to_dict(),
    }

    md = _synthesize(
        n_sessions=n_sessions,
        s_l14_full=s_l14_full, s_l14_minus=s_l14_minus,
        s_l20_full=s_l20_full, s_l20_minus=s_l20_minus,
        s_z_full=s_z_full, s_z_minus=s_z_minus,
        pc14=pc14, pc20=pc20, pcz=pcz,
        overlay_both=both, overlay_only_locked=only_locked,
        overlay_only_zach=only_zach,
        overlay_df=overlay,
        exit_dists=exit_dists,
    )
    OUT_MD.write_text(md)
    print(f"\nSaved synthesis: {OUT_MD}")
    return 0


def _3way_row(label: str, s_l14, s_l20, s_z) -> str:
    return (f"| {label} | "
            f"{s_l14} | {s_l20} | {s_z} |")


def _synthesize(**kw) -> str:
    L: list[str] = []
    L.append("# OMEN — Zach May parameter comparison (THROWAWAY)\n")
    L.append("Branch: `analysis/omen-minus-sl-quickcheck-throwaway` "
             "(throwaway / archive only; never merges to main).")
    L.append(f"Generated: {datetime.now().isoformat(timespec='seconds')}\n")
    L.append("## 1. Disclosure\n")
    L.append(ZACH_DISCLOSURE)
    L.append("")

    L.append("## 2. Parameter sets compared\n")
    L.append("| param | locked-14 (orig quick-check) | locked-20 (ATR sensitivity) | Zach May |")
    L.append("|---|---|---|---|")
    L.append("| z_threshold | 1.8 | 1.8 | **2.0** |")
    L.append("| stop_atr_mult | 2.0 | 2.0 | 2.0 |")
    L.append("| target_atr_mult | 4.5 | 4.5 | **5.0** |")
    L.append("| time_stop_min | 25 | 25 | **35** |")
    L.append("| atr_window_bars | 14 | **20** | 14 |")
    L.append("| blackout_lunch | True | True | True |")
    L.append("| bar_freq | 5min | 5min | 5min |")
    L.append("")
    L.append(f"Sessions analyzed: **{kw['n_sessions']}** "
             "(2026-04-30 → 2026-05-11; same set across all three runs).")
    L.append("")

    # Side-by-side table
    L.append("## 3. Three-way side-by-side comparison\n")
    s14 = kw["s_l14_full"]; s20 = kw["s_l20_full"]; sz = kw["s_z_full"]
    s14m = kw["s_l14_minus"]; s20m = kw["s_l20_minus"]; szm = kw["s_z_minus"]
    pc14 = kw["pc14"]; pc20 = kw["pc20"]; pcz = kw["pcz"]

    L.append("| metric | locked (ATR=14) | locked (ATR=20) | Zach May |")
    L.append("|---|---:|---:|---:|")
    L.append(_3way_row("N total trades", s14["n"], s20["n"], sz["n"]))
    L.append(_3way_row("Cell counts (LL/LS/SL/SS)",
                       f"{pc14['LONG_long']['n']}/{pc14['LONG_short']['n']}/{pc14['SHORT_long']['n']}/{pc14['SHORT_short']['n']}",
                       f"{pc20['LONG_long']['n']}/{pc20['LONG_short']['n']}/{pc20['SHORT_long']['n']}/{pc20['SHORT_short']['n']}",
                       f"{pcz['LONG_long']['n']}/{pcz['LONG_short']['n']}/{pcz['SHORT_long']['n']}/{pcz['SHORT_short']['n']}"))
    L.append(_3way_row("Full OMEN win rate",
                       _fmt_wr(s14["win_rate"]), _fmt_wr(s20["win_rate"]),
                       _fmt_wr(sz["win_rate"])))
    L.append(_3way_row("Full OMEN mean $",
                       f"${s14['mean']:+.2f}", f"${s20['mean']:+.2f}",
                       f"${sz['mean']:+.2f}"))
    L.append(_3way_row("Full OMEN sum $",
                       f"${s14['sum']:+.0f}", f"${s20['sum']:+.0f}",
                       f"${sz['sum']:+.0f}"))
    L.append(_3way_row("Full OMEN Sharpe",
                       _fmt_sh(s14["sharpe"]), _fmt_sh(s20["sharpe"]),
                       _fmt_sh(sz["sharpe"])))
    L.append(_3way_row("Full OMEN max DD",
                       f"${s14['max_dd']:+.0f}", f"${s20['max_dd']:+.0f}",
                       f"${sz['max_dd']:+.0f}"))
    L.append(_3way_row("Minus-SL N",
                       s14m["n"], s20m["n"], szm["n"]))
    L.append(_3way_row("Minus-SL win rate",
                       _fmt_wr(s14m["win_rate"]), _fmt_wr(s20m["win_rate"]),
                       _fmt_wr(szm["win_rate"])))
    L.append(_3way_row("Minus-SL sum $",
                       f"${s14m['sum']:+.0f}", f"${s20m['sum']:+.0f}",
                       f"${szm['sum']:+.0f}"))
    L.append(_3way_row("Minus-SL Sharpe",
                       _fmt_sh(s14m["sharpe"]), _fmt_sh(s20m["sharpe"]),
                       _fmt_sh(szm["sharpe"])))
    L.append("")

    # Trade-level overlay
    L.append("## 4. Trade-level overlay — locked-14 vs Zach May\n")
    L.append("FlowBurst entries depend on `gexoflow_z` ≥ z_threshold. Zach uses 2.0 vs ")
    L.append("locked 1.8, so Zach should produce a *subset* of locked-14's entries plus ")
    L.append("potential mismatches near the threshold. Exit reasons and PnL change due ")
    L.append("to the wider target (5.0×ATR) and longer time stop (35min vs 25min).")
    L.append("")
    L.append(f"- Trades present in **both** (matched on entry_time + side + gamma_regime): "
             f"**{kw['overlay_both']}**")
    L.append(f"- Trades only in locked-14: **{kw['overlay_only_locked']}** "
             "(filtered out by z_threshold=2.0)")
    L.append(f"- Trades only in Zach May: **{kw['overlay_only_zach']}** "
             "(unexpected if Zach is a strict subset — investigate if non-zero)")
    L.append("")
    # If there are exit-reason changes among matched trades, surface
    matched = kw["overlay_df"][kw["overlay_df"]["_merge"] == "both"].copy()
    if len(matched) > 0:
        same_exit = int((matched["exit_reason_l14"] == matched["exit_reason_z"]).sum())
        L.append(f"- Among the {len(matched)} matched trades, **{same_exit}** have the "
                 f"same `exit_reason` under both parameter sets; "
                 f"**{len(matched) - same_exit}** change exit reason "
                 "(typically locked time → Zach target, or locked time → Zach time).")
    L.append("")
    L.append("### Exit-reason distribution per parameter set\n")
    L.append("| param set | time | stop | target | session_close |")
    L.append("|---|---:|---:|---:|---:|")
    for label, key in (("locked-14", "locked_14"), ("locked-20", "locked_20"),
                        ("Zach May", "zach_may")):
        d = kw["exit_dists"][key]
        L.append(f"| {label} | {d.get('time',0)} | {d.get('stop',0)} | "
                 f"{d.get('target',0)} | {d.get('session_close',0)} |")
    L.append("")

    # Per-cell Zach
    L.append("## 5. Per-cell breakdown — Zach May params\n")
    L.append("| cell | N | mean $ | sum $ |")
    L.append("|---|---:|---:|---:|")
    for c in CELLS:
        L.append(f"| {c} | {pcz[c]['n']} | ${pcz[c]['mean']:+.2f} | ${pcz[c]['sum']:+.0f} |")
    L.append("")
    # SHORT_long note
    if pcz["SHORT_long"]["n"] == 0:
        L.append("**Notable: Zach's params produced ZERO `SHORT_long` trades on this window.** ")
        L.append("That means the OMEN-minus-SL exclusion is **vacuous** under Zach's params on ")
        L.append("this sample — there's nothing to exclude — so the minus-SL Sharpe equals the ")
        L.append("full Sharpe by construction. The original quick-check's directional finding ")
        L.append("(minus-SL > full) cannot be tested under these params on these sessions.")
    L.append("")

    # Honest interpretation
    L.append("## 6. Honest interpretation\n")
    L.append("**Trade count changed substantially.** Locked z=1.8 → 18 trades, Zach z=2.0 → "
             f"{sz['n']} trades on the same 8 sessions. The higher z_threshold filters out "
             f"~{s14['n'] - sz['n']} signals, all of which would have fired under locked-14.")
    L.append("")
    L.append("**Direct Sharpe comparison is contaminated.** Three different parameter sets ")
    L.append("on the same 8-session sample is exactly the kind of multiple-comparison setup ")
    L.append("that produces false 'winners' from noise. With ~14-18 trades per arm, any ")
    L.append("ranking we observe could easily flip on the next 8 sessions.")
    L.append("")
    if sz["sharpe"] is not None and s14["sharpe"] is not None:
        better = "higher" if sz["sharpe"] > s14["sharpe"] else "lower"
        L.append(f"**Zach's full Sharpe ({_fmt_sh(sz['sharpe'])}) is {better} than ")
        L.append(f"locked-14's ({_fmt_sh(s14['sharpe'])}).** That's a data point, not a verdict. ")
        L.append(f"Possible explanations include: (a) the wider target/longer time-stop happened ")
        L.append("to capture moves that locked-14's tighter exits clipped, (b) the higher ")
        L.append("z_threshold happened to filter out a couple of losing trades on these ")
        L.append("sessions, (c) coincidence. At n=14-18, distinguishing between these is ")
        L.append("statistically impossible.")
    L.append("")
    L.append("**The OMEN-minus-SL diagnostic is uninformative under Zach's params here** ")
    L.append("because the SHORT_long cell didn't fire at all. The original quick-check's ")
    L.append("hypothesis (minus-SL improves Sharpe) **can't be tested** in the Zach arm.")
    L.append("")
    L.append("**What this result tells us about which parameter set is 'better':** ")
    L.append("**almost nothing.** Both are running on 18 and 14 trades respectively over 8 ")
    L.append("sessions. Any conclusion needs (a) provenance for Zach's params, (b) ≥30 ")
    L.append("fresh sessions, (c) a pre-registered test that locked the comparison BEFORE ")
    L.append("seeing this data. None of those conditions are met.")
    L.append("")

    # Caveats
    L.append("## 7. Caveats (mandatory)\n")
    L.append("- **18 / 14 trades is too small for any verdict.** Period.")
    L.append("- **Provenance of Zach's params is unknown.** They could be mechanistically ")
    L.append("  derived, pre-registered, monthly tuned, or random — we don't know. Without ")
    L.append("  provenance, any positive read is uninterpretable as evidence of edge.")
    L.append("- **Same 8 fresh sessions used for a third analysis.** This data pool is now ")
    L.append("  more consumed than it was at the start of the quick-check. Future fresh-")
    L.append("  data work that touches Apr 30 → May 11 will need to account for the multiple ")
    L.append("  parameter-set looks on this window.")
    L.append("- **No deployment, no baseline switch, no claim of 'Zach's params are better' ")
    L.append("  based on this result.** Hard rule, applies regardless of the numbers above.")
    if sz["n"] < 10:
        L.append(f"- **Zach's trade count ({sz['n']}) is below the n=10 threshold for ")
        L.append("  Sharpe estimation.** Sharpe omitted; per-cell sums reported only.")
    elif sz["n"] < 30:
        L.append(f"- **Zach's trade count ({sz['n']}) is within the noise-dominated range** ")
        L.append("  for Sharpe estimation. Standard error on the Sharpe estimate is enormous.")
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
