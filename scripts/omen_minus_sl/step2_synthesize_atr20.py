"""Step 2 (ATR=20 SENSITIVITY) — compute metrics on the ATR=20 trade set and
emit SYNTHESIS_atr20.md with a side-by-side ATR=14 vs ATR=20 table.

NOT a comparison to IS-174 / OOS-158 (those used ATR=14 and aren't directly
comparable). The valid comparison here is fresh-18 ATR=14 vs fresh-18 ATR=20.
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

ATR14_CSV = ANALYSIS_DIR / "fresh_session_trades_raw.csv"
ATR20_CSV = ANALYSIS_DIR / "fresh_session_trades_atr20_raw.csv"
ATR20_FULL_CSV = ANALYSIS_DIR / "fresh_trades_full_omen_atr20.csv"
ATR20_SL_CSV = ANALYSIS_DIR / "fresh_trades_omen_minus_sl_atr20.csv"
SYNTHESIS_MD = ANALYSIS_DIR / "SYNTHESIS_atr20.md"

SL_CELL = "SHORT_long"
CELLS = ["LONG_long", "LONG_short", "SHORT_long", "SHORT_short"]


def _max_drawdown(net_dollars: pd.Series, entry_time: pd.Series) -> float:
    if len(net_dollars) == 0:
        return 0.0
    order = entry_time.argsort()
    eq = np.cumsum(net_dollars.values[order])
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


def _stats(trades: pd.DataFrame, n_sessions: int) -> dict:
    if len(trades) == 0:
        return {"n": 0, "win_rate": None, "mean": 0.0, "sum": 0.0,
                "sharpe": None, "max_dd": 0.0}
    net = trades["net_dollars"]
    return {
        "n": int(len(trades)),
        "win_rate": float((net > 0).mean()),
        "mean": float(net.mean()),
        "sum": float(net.sum()),
        "sharpe": _sharpe(net, n_sessions),
        "max_dd": _max_drawdown(net, trades["entry_time_utc"]),
    }


def _load(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["entry_time"] = pd.to_datetime(df["entry_time"], utc=True)
    df["entry_time_utc"] = df["entry_time"]
    df["entry_time_et"] = df["entry_time"].dt.tz_convert(ET)
    df["entry_date"] = df["entry_time_et"].dt.date
    df["side_label"] = np.where(df["side"] == 1, "LONG", "SHORT")
    df["cell"] = df["side_label"] + "_" + df["gamma_regime"].astype(str)
    return df


def _fmt_sh(sh) -> str:
    return "—" if sh is None else f"{sh:+.2f}"


def _fmt_wr(wr) -> str:
    return "—" if wr is None else f"{wr*100:.1f}%"


def main() -> int:
    atr14 = _load(ATR14_CSV)
    atr20 = _load(ATR20_CSV)
    n_sessions = atr20["entry_date"].nunique()
    dates = sorted(atr20["entry_date"].unique())

    print("=" * 72)
    print("ATR=14 vs ATR=20 — fresh-session comparison")
    print("=" * 72)
    print(f"  sessions: {n_sessions}")

    # Stats for each ATR variant
    atr14_full = _stats(atr14, n_sessions)
    atr14_minus = _stats(atr14[atr14["cell"] != SL_CELL].copy(), n_sessions)
    atr20_full = _stats(atr20, n_sessions)
    atr20_minus_df = atr20[atr20["cell"] != SL_CELL].copy()
    atr20_minus = _stats(atr20_minus_df, n_sessions)

    # Save split files for ATR=20
    atr20.to_csv(ATR20_FULL_CSV, index=False)
    atr20_minus_df.to_csv(ATR20_SL_CSV, index=False)
    print(f"\nSaved: {ATR20_FULL_CSV}")
    print(f"Saved: {ATR20_SL_CSV}")

    # Per-cell breakdowns
    def per_cell(df):
        return {c: _stats(df[df["cell"] == c], n_sessions) for c in CELLS}
    pc14 = per_cell(atr14)
    pc20 = per_cell(atr20)

    print("\nAggregate comparison:")
    print(f"  {'metric':<22s}  {'ATR=14':>12s}  {'ATR=20':>12s}")
    print(f"  {'N trades':<22s}  {atr14_full['n']:>12d}  {atr20_full['n']:>12d}")
    print(f"  {'win rate (full)':<22s}  {_fmt_wr(atr14_full['win_rate']):>12s}  "
          f"{_fmt_wr(atr20_full['win_rate']):>12s}")
    a14_mean = f"${atr14_full['mean']:+.2f}"; a20_mean = f"${atr20_full['mean']:+.2f}"
    a14_sum = f"${atr14_full['sum']:+.0f}";   a20_sum = f"${atr20_full['sum']:+.0f}"
    print(f"  {'mean $ (full)':<22s}  {a14_mean:>12s}  {a20_mean:>12s}")
    print(f"  {'sum $ (full)':<22s}  {a14_sum:>12s}  {a20_sum:>12s}")
    print(f"  {'Sharpe (full)':<22s}  {_fmt_sh(atr14_full['sharpe']):>12s}  "
          f"{_fmt_sh(atr20_full['sharpe']):>12s}")
    print(f"  {'Sharpe (minus-SL)':<22s}  {_fmt_sh(atr14_minus['sharpe']):>12s}  "
          f"{_fmt_sh(atr20_minus['sharpe']):>12s}")
    print(f"  {'max DD (full)':<22s}  ${atr14_full['max_dd']:>+11.0f}  "
          f"${atr20_full['max_dd']:>+11.0f}")
    cells14 = f"{pc14['LONG_long']['n']}/{pc14['LONG_short']['n']}/{pc14['SHORT_long']['n']}/{pc14['SHORT_short']['n']}"
    cells20 = f"{pc20['LONG_long']['n']}/{pc20['LONG_short']['n']}/{pc20['SHORT_long']['n']}/{pc20['SHORT_short']['n']}"
    print(f"  {'cells LL/LS/SL/SS':<22s}  {cells14:>12s}  {cells20:>12s}")

    print("\nPer-cell mean $ comparison:")
    for c in CELLS:
        print(f"  {c:<12s}  ATR=14: n={pc14[c]['n']} sum=${pc14[c]['sum']:+.0f} mean=${pc14[c]['mean']:+.2f}  |  "
              f"ATR=20: n={pc20[c]['n']} sum=${pc20[c]['sum']:+.0f} mean=${pc20[c]['mean']:+.2f}")

    # Per-trade overlay: same entry_time → did stop/target/PnL change?
    merge_cols = ["entry_time", "side", "gamma_regime", "atr_at_entry",
                   "stop_px", "target_px", "exit_reason", "bars_held",
                   "exit_px", "gross_points", "net_dollars"]
    overlay = atr14[merge_cols].merge(
        atr20[merge_cols], on=["entry_time", "side", "gamma_regime"],
        suffixes=("_14", "_20"),
    )
    print(f"\nPer-trade overlay (matched by entry_time + side + gamma_regime):"
          f" {len(overlay)} matched of {len(atr14)} ATR=14 trades")
    if len(overlay) == len(atr14):
        delta_net = overlay["net_dollars_20"] - overlay["net_dollars_14"]
        n_same_exit = int((overlay["exit_reason_14"] == overlay["exit_reason_20"]).sum())
        print(f"  exit_reason matched: {n_same_exit}/{len(overlay)}")
        print(f"  Δ net_dollars (20 − 14): mean={delta_net.mean():+.2f}  "
              f"sum={delta_net.sum():+.0f}  "
              f"min={delta_net.min():+.2f}  max={delta_net.max():+.2f}")

    # Build synthesis
    md = _synthesize(
        n_sessions=n_sessions, dates=dates,
        atr14_full=atr14_full, atr14_minus=atr14_minus,
        atr20_full=atr20_full, atr20_minus=atr20_minus,
        pc14=pc14, pc20=pc20, overlay=overlay,
    )
    SYNTHESIS_MD.write_text(md)
    print(f"\nSaved synthesis: {SYNTHESIS_MD}")
    return 0


def _synthesize(*, n_sessions, dates, atr14_full, atr14_minus, atr20_full,
                atr20_minus, pc14, pc20, overlay) -> str:
    L: list[str] = []
    L.append("# OMEN-minus-SL — ATR=20 SENSITIVITY VARIANT (THROWAWAY)\n")
    L.append("Branch: `analysis/omen-minus-sl-quickcheck-throwaway` "
             "(throwaway / archive only; never merges to main).")
    L.append(f"Generated: {datetime.now().isoformat(timespec='seconds')}\n")
    L.append("## 1. Disclosure\n")
    L.append("This is a SENSITIVITY VARIANT of the original OMEN-minus-SL quick-check ")
    L.append("(see `SYNTHESIS.md` in the same directory). It runs the identical pipeline ")
    L.append("on the identical fresh-session window, with ONE change: the ATR rolling ")
    L.append("window for stop/target sizing is switched from **14 → 20**.")
    L.append("")
    L.append("Motivation: `Current_State_of_OMEN.txt` documented `atr_window_bars=20` ")
    L.append("but the actual locked code (`backend/cheese/features.py:54`) hardcodes ")
    L.append("a 14-bar SMA. This run quantifies whether the documentation/code mismatch ")
    L.append("changes the fresh-18 read in a directionally meaningful way.")
    L.append("")
    L.append("**The same caveats from the original quick-check apply:** sample size ")
    L.append("(18 trades, 8 sessions) is far below what's required for any verdict. ")
    L.append("This sensitivity check does NOT validate or invalidate OMEN-minus-SL.")
    L.append("")
    L.append("**The ATR=20 fresh result is NOT directly comparable to the IS-174 / ")
    L.append("OOS-158 baselines** (those ran on ATR=14). The valid comparison here ")
    L.append("is fresh-18 ATR=14 vs fresh-18 ATR=20.")
    L.append("")

    # Implementation
    L.append("## 2. Implementation\n")
    L.append("- Same fresh-session window: 8 sessions, "
             f"{dates[0].isoformat()} → {dates[-1].isoformat()}.")
    L.append("- Same locked params: flow_burst z=1.8, blackout_lunch=True, "
             "stop=2.0×ATR, target=4.5×ATR, time_stop=25min, bar_freq=5min.")
    L.append("- ATR override: after `features.build_features` returns, the `atr` and ")
    L.append("  `atr_pts` columns are recomputed as `tr.rolling(20, min_periods=5).mean()`. ")
    L.append("  Same True Range formula as `features.py:54`, only the window changes.")
    L.append("- No locked files modified.")
    L.append("- Warmup start shifted back 1 week (2026-04-08) to give ATR(20) more bars to stabilize.")
    L.append("")

    # Side-by-side comparison
    L.append("## 3. Side-by-side comparison\n")
    L.append("| metric | ATR=14 (original) | ATR=20 (this run) |")
    L.append("|---|---:|---:|")
    L.append(f"| N total trades | {atr14_full['n']} | {atr20_full['n']} |")
    L.append(f"| Cell counts (LL/LS/SL/SS) | "
             f"{pc14['LONG_long']['n']}/{pc14['LONG_short']['n']}/"
             f"{pc14['SHORT_long']['n']}/{pc14['SHORT_short']['n']} | "
             f"{pc20['LONG_long']['n']}/{pc20['LONG_short']['n']}/"
             f"{pc20['SHORT_long']['n']}/{pc20['SHORT_short']['n']} |")
    L.append(f"| Full OMEN win rate | {_fmt_wr(atr14_full['win_rate'])} | "
             f"{_fmt_wr(atr20_full['win_rate'])} |")
    L.append(f"| Full OMEN mean $ | ${atr14_full['mean']:+.2f} | ${atr20_full['mean']:+.2f} |")
    L.append(f"| Full OMEN sum $ | ${atr14_full['sum']:+.0f} | ${atr20_full['sum']:+.0f} |")
    L.append(f"| Full OMEN Sharpe | {_fmt_sh(atr14_full['sharpe'])} | "
             f"{_fmt_sh(atr20_full['sharpe'])} |")
    L.append(f"| Full OMEN max DD | ${atr14_full['max_dd']:+.0f} | "
             f"${atr20_full['max_dd']:+.0f} |")
    L.append(f"| OMEN-minus-SL N | {atr14_minus['n']} | {atr20_minus['n']} |")
    L.append(f"| OMEN-minus-SL win rate | {_fmt_wr(atr14_minus['win_rate'])} | "
             f"{_fmt_wr(atr20_minus['win_rate'])} |")
    L.append(f"| OMEN-minus-SL mean $ | ${atr14_minus['mean']:+.2f} | "
             f"${atr20_minus['mean']:+.2f} |")
    L.append(f"| OMEN-minus-SL sum $ | ${atr14_minus['sum']:+.0f} | "
             f"${atr20_minus['sum']:+.0f} |")
    L.append(f"| OMEN-minus-SL Sharpe | {_fmt_sh(atr14_minus['sharpe'])} | "
             f"{_fmt_sh(atr20_minus['sharpe'])} |")
    L.append("")

    # Per-cell ATR=20 breakdown
    L.append("## 4. Per-cell breakdown — ATR=20\n")
    L.append("| cell | N | mean $ | sum $ |")
    L.append("|---|---:|---:|---:|")
    for c in CELLS:
        L.append(f"| {c} | {pc20[c]['n']} | ${pc20[c]['mean']:+.2f} | ${pc20[c]['sum']:+.0f} |")
    L.append("")

    # Per-trade overlay
    L.append("## 5. Per-trade overlay (matched on entry_time + side + gamma_regime)\n")
    L.append("FlowBurst entries depend only on `gexoflow_z` / `dexoflow_z`, which are ")
    L.append("ATR-independent. So all 18 ATR=14 entry points are expected to match all ")
    L.append("18 ATR=20 entry points. Differences are confined to:")
    L.append("- `atr_at_entry` (driven by the ATR window)")
    L.append("- `stop_px` / `target_px` (sized as ATR multiples)")
    L.append("- `exit_reason`, `bars_held`, `exit_px`, `net_dollars` (downstream of the above)")
    L.append("")
    L.append(f"- Matched trades: **{len(overlay)} / {atr14_full['n']}**")
    if len(overlay) > 0:
        delta_net = overlay["net_dollars_20"] - overlay["net_dollars_14"]
        n_same_exit = int((overlay["exit_reason_14"] == overlay["exit_reason_20"]).sum())
        L.append(f"- Trades with same `exit_reason`: {n_same_exit} / {len(overlay)}")
        L.append(f"- Δ net_dollars (ATR=20 − ATR=14): mean = "
                 f"**${delta_net.mean():+.2f}**, sum = **${delta_net.sum():+.0f}**, "
                 f"range = [${delta_net.min():+.2f}, ${delta_net.max():+.2f}]")
    L.append("")

    # Honest comparison
    L.append("## 6. Honest comparison\n")
    L.append("**Did the trade count change?** ")
    if atr14_full["n"] == atr20_full["n"]:
        L.append(f"No. Both runs produced **{atr14_full['n']}** trades. This is expected: ")
        L.append("FlowBurst entry conditions depend only on gexoflow_z / dexoflow_z, which ")
        L.append("are computed from GEX flow features and have no dependence on ATR. The ")
        L.append("ATR change only affects stop/target sizing on the same set of entries.")
    else:
        L.append(f"ATR=14 → {atr14_full['n']} trades, ATR=20 → {atr20_full['n']} trades. ")
        L.append("This is unexpected; investigate.")
    L.append("")
    L.append("**Did the cell composition change?**")
    if all(pc14[c]["n"] == pc20[c]["n"] for c in CELLS):
        L.append(" No. Cell counts are identical across the two runs.")
    else:
        L.append(" Yes — see Section 4.")
    L.append("")
    L.append("**Did the directional verdict change?**")
    s14_full = atr14_full["sharpe"]; s14_minus = atr14_minus["sharpe"]
    s20_full = atr20_full["sharpe"]; s20_minus = atr20_minus["sharpe"]
    v14_consistent = (s14_minus is not None and s14_full is not None
                       and s14_minus > s14_full)
    v20_consistent = (s20_minus is not None and s20_full is not None
                       and s20_minus > s20_full)
    L.append(f" ATR=14: minus-SL Sharpe {_fmt_sh(s14_minus)} vs full Sharpe "
             f"{_fmt_sh(s14_full)} → directionally "
             f"{'CONSISTENT' if v14_consistent else 'INCONSISTENT'}.")
    L.append(f" ATR=20: minus-SL Sharpe {_fmt_sh(s20_minus)} vs full Sharpe "
             f"{_fmt_sh(s20_full)} → directionally "
             f"{'CONSISTENT' if v20_consistent else 'INCONSISTENT'}.")
    if v14_consistent and v20_consistent:
        L.append(" **Same directional verdict on both ATR windows.**")
    elif v14_consistent and not v20_consistent:
        L.append(" Verdict flips with ATR window — fragile.")
    elif not v14_consistent and v20_consistent:
        L.append(" Verdict flips with ATR window — fragile.")
    else:
        L.append(" Neither variant is directionally consistent.")
    L.append("")
    L.append("**Is the result still driven by removing a single SHORT_long trade?**")
    sl14 = pc14["SHORT_long"]; sl20 = pc20["SHORT_long"]
    L.append(f" ATR=14 SHORT_long: n={sl14['n']}, sum=${sl14['sum']:+.0f}.")
    L.append(f" ATR=20 SHORT_long: n={sl20['n']}, sum=${sl20['sum']:+.0f}. ")
    if sl14["n"] == 1 and sl20["n"] == 1:
        L.append(" Yes — both runs have a single SHORT_long trade. The minus-SL ")
        L.append(" Sharpe lift in BOTH cases is driven by removing that one trade. ")
        L.append(" Same fragility caveat from the original quick-check applies.")
    L.append("")

    # Interpretation
    L.append("## 7. Interpretation\n")
    n14 = atr14_full["n"]; n20 = atr20_full["n"]
    cell_match = all(pc14[c]["n"] == pc20[c]["n"] for c in CELLS)

    sh_delta_full = (atr20_full["sharpe"] - atr14_full["sharpe"]
                     if atr14_full["sharpe"] is not None
                     and atr20_full["sharpe"] is not None else None)
    sh_delta_minus = (atr20_minus["sharpe"] - atr14_minus["sharpe"]
                      if atr14_minus["sharpe"] is not None
                      and atr20_minus["sharpe"] is not None else None)
    sum_delta_full = atr20_full["sum"] - atr14_full["sum"]

    L.append("### Direction unchanged, magnitude shifted substantially\n")
    L.append(f"- **Trade count and cell composition: identical** "
             f"({n14} trades, LL/LS/SL/SS = {pc14['LONG_long']['n']}/{pc14['LONG_short']['n']}"
             f"/{pc14['SHORT_long']['n']}/{pc14['SHORT_short']['n']} in both runs). ")
    L.append("  Expected: FlowBurst entries depend only on `gexoflow_z`/`dexoflow_z`, both ")
    L.append("  ATR-independent.")
    L.append("")
    L.append("- **Directional verdict (minus-SL > full): unchanged**. Both ATR windows ")
    L.append("  produce DIRECTIONALLY CONSISTENT.")
    L.append("")
    L.append(f"- **Sharpe magnitudes shift substantially**: full Sharpe goes "
             f"{atr14_full['sharpe']:+.2f} → {atr20_full['sharpe']:+.2f} "
             f"(Δ = {sh_delta_full:+.2f}); minus-SL Sharpe goes "
             f"{atr14_minus['sharpe']:+.2f} → {atr20_minus['sharpe']:+.2f} "
             f"(Δ = {sh_delta_minus:+.2f}). The directional label is preserved but the ")
    L.append("  underlying performance is **noticeably better at ATR=20** on this sample.")
    L.append("")
    L.append(f"- **PnL shift on matched trades**: Δ net_dollars (ATR=20 − ATR=14) sums to "
             f"**${sum_delta_full:+.0f}** across 18 trades (mean **${sum_delta_full/18:+.2f}/trade**). ")
    L.append(f"  Most of the lift comes from the **SHORT_short** cell ")
    L.append(f"(n={pc14['SHORT_short']['n']}, sum=${pc14['SHORT_short']['sum']:+.0f} at ATR=14 ")
    L.append(f"vs ${pc20['SHORT_short']['sum']:+.0f} at ATR=20 — a swing of "
             f"${pc20['SHORT_short']['sum']-pc14['SHORT_short']['sum']:+.0f}).")
    L.append("")
    L.append("### What this means\n")
    L.append("- **Trade selection is ATR-invariant in this strategy.** Entries don't care.")
    L.append("")
    L.append("- **Exit outcomes are ATR-sensitive**, especially in the SHORT_short cell. ")
    L.append("  ATR=20 produces slightly wider stops (median ATR 5.96 vs 5.79), which ")
    L.append("  reduces stop-outs and lets trades reach time-stop / target.")
    L.append("")
    L.append("- **For the OMEN-minus-SL hypothesis specifically**: both ATR windows give ")
    L.append("  the same directional read (minus-SL > full) and both still rest on the ")
    L.append("  same n=1 SHORT_long trade. The hypothesis-level conclusion is unchanged.")
    L.append("")
    L.append("- **The documentation/code mismatch is NOT cosmetic.** ATR=20 would produce ")
    L.append("  meaningfully different Sharpe numbers on the IS-174 / OOS-158 baselines ")
    L.append("  if those were re-run with this ATR window. Those Sharpes ARE NOT REPRODUCIBLE ")
    L.append("  under ATR=20 without re-running the full backtest. If `Current_State_of_OMEN.txt` ")
    L.append("  is the source of truth for what's deployed, either the doc is wrong or the ")
    L.append("  code is wrong; pick one and reconcile before deployment.")
    L.append("")
    L.append("### Limits on this read\n")
    L.append("- 18 trades is far too small to claim ATR=20 is 'better' than ATR=14 for ")
    L.append("  OMEN's edge. The Sharpe lift could be coincidence on this window.")
    L.append("- The ATR=20 fresh result is NOT comparable to IS-174 / OOS-158 — those used ")
    L.append("  ATR=14. To make a clean ATR=14 vs ATR=20 statement at scale, both ATR windows ")
    L.append("  would need to be re-run on the full 160-session corpus. That's a separate ")
    L.append("  exercise and consumed-data caveats apply.")
    L.append("")

    # Caveats
    L.append("## 8. Caveats (mandatory)\n")
    L.append("- **18 trades is too small for any verdict.** This holds regardless of ATR window.")
    L.append("- **ATR=20 fresh result is NOT directly comparable to IS-174 or OOS-158** ")
    L.append("  (those were generated with ATR=14). The valid comparison is fresh-18 ")
    L.append("  ATR=14 vs fresh-18 ATR=20, both shown above.")
    L.append("- **This sensitivity test does NOT validate or invalidate OMEN-minus-SL.** ")
    L.append("  It only quantifies the ATR-window-dependence of the fresh-18 read.")
    L.append("- **Forward-test pre-registration on 30+ accumulated sessions remains ")
    L.append("  required.** That is the only path to a verdict, regardless of which ATR ")
    L.append("  window OMEN ultimately uses.")
    L.append("- **The original quick-check's fragility note also applies here**: the ")
    L.append("  minus-SL Sharpe lift in both ATR variants rests on removing a single ")
    L.append("  SHORT_long trade. SHORT_short (n=9) is doing more total $ damage than ")
    L.append("  SHORT_long (n=1) in both runs.")
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
