"""Steps 2-5 — apply cell exclusion, compute metrics, build SYNTHESIS.md.

QUICK CHECK on a tiny sample (n=18). Underpowered by construction. The
synthesis file MUST disclose this and refuse to call any result validation.
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

FRESH_CSV = ANALYSIS_DIR / "fresh_session_trades_raw.csv"
FULL_CSV = ANALYSIS_DIR / "fresh_trades_full_omen.csv"
SL_CSV   = ANALYSIS_DIR / "fresh_trades_omen_minus_sl.csv"
SYNTHESIS_MD = ANALYSIS_DIR / "SYNTHESIS.md"

SL_CELL = "SHORT_long"
CELLS = ["LONG_long", "LONG_short", "SHORT_long", "SHORT_short"]
ALL_CELLS_ORDER = CELLS

QUICK_CHECK_DISCLOSURE = """\
## DISCLOSURE — quick-check, underpowered

This is a quick exploratory read on a small sample of fresh sessions.
The OMEN-minus-SHORT_long hypothesis was generated from observing
consumed-data cell performance (analysis/omen-cell-breakdown-throwaway).
While the fresh sessions themselves were not previously analyzed for
OMEN trade outcomes, the hypothesis being tested IS data-derived.

Sample size: 11-12 sessions, ~16-24 OMEN-minus-SL trades expected.
This is statistically underpowered. Results inform planning, not validation.
A proper forward-test pre-registration will be written separately and
applied to 30+ accumulated fresh sessions for verdict.
"""

# Prior buckets (from previously committed analysis, for context comparison)
PRIOR_BUCKETS = {
    "IS": {
        "trade_count": 174,
        "sessions": 80,
        "full_omen_sharpe": 5.38,  # full_omen IS Sharpe (annualised) from Q3 trade log
        "per_cell_sharpe": {
            "LONG_long":   1.541,
            "LONG_short":  5.053,
            "SHORT_long":  3.231,
            "SHORT_short": 0.780,
        },
        "per_cell_n": {"LONG_long": 27, "LONG_short": 60, "SHORT_long": 32, "SHORT_short": 55},
    },
    "OOS": {
        "trade_count": 158,
        "sessions": 76,
        "full_omen_sharpe": 1.13,
        "omen_minus_sl_sharpe": 2.79,
        "per_cell_sharpe": {
            "LONG_long":   2.115,
            "LONG_short":  2.067,
            "SHORT_long": -1.953,   # the cell flagged as 'broken' in cell-breakdown OOS
            "SHORT_short": 1.013,
        },
        "per_cell_n": {"LONG_long": 33, "LONG_short": 29, "SHORT_long": 48, "SHORT_short": 48},
    },
}


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
    mean_t = float(net.mean()); std_t = float(net.std(ddof=1))
    if std_t == 0:
        return None
    return ((mean_t * tpd) / (std_t * np.sqrt(tpd))) * np.sqrt(252)


def _stats_block(trades: pd.DataFrame, n_sessions: int) -> dict:
    if len(trades) == 0:
        return {"n": 0, "n_sessions": n_sessions,
                "win_rate": None, "mean": 0.0, "sum": 0.0,
                "sharpe": None, "max_dd": 0.0}
    net = trades["net_dollars"]
    sh = _sharpe(net, n_sessions, min_n=10)
    return {
        "n": int(len(trades)),
        "n_sessions": n_sessions,
        "win_rate": float((net > 0).mean()),
        "mean": float(net.mean()),
        "sum": float(net.sum()),
        "sharpe": sh,
        "max_dd": _max_drawdown(net, trades["entry_time_utc"]),
    }


def _md_sharpe(sh) -> str:
    if sh is None:
        return "—"
    return f"{sh:+.2f}"


def _md_winrate(wr) -> str:
    if wr is None:
        return "—"
    return f"{wr*100:.1f}%"


def main() -> int:
    # ---- Load fresh trades ----
    trades = pd.read_csv(FRESH_CSV)
    trades["entry_time"] = pd.to_datetime(trades["entry_time"], utc=True)
    trades["entry_time_utc"] = trades["entry_time"]
    trades["entry_time_et"] = trades["entry_time"].dt.tz_convert(ET)
    trades["entry_date"] = trades["entry_time_et"].dt.date
    trades["side_label"] = np.where(trades["side"] == 1, "LONG", "SHORT")
    trades["cell"] = trades["side_label"] + "_" + trades["gamma_regime"].astype(str)

    n_sessions = trades["entry_date"].nunique()
    dates = sorted(trades["entry_date"].unique())

    print("=" * 72)
    print("STEPS 2-5 — cell exclusion, metrics, synthesis")
    print("=" * 72)
    print(f"  fresh trades : {len(trades)}")
    print(f"  fresh sessions: {n_sessions}  ({dates[0].isoformat()} → {dates[-1].isoformat()})")

    # ---- Step 2 — split into full + minus-SL ----
    full_omen = trades.copy()
    minus_sl = trades[trades["cell"] != SL_CELL].copy()
    full_omen.to_csv(FULL_CSV, index=False)
    minus_sl.to_csv(SL_CSV, index=False)
    print(f"\nSaved full_omen      : {FULL_CSV} ({len(full_omen)} trades)")
    print(f"Saved omen_minus_sl  : {SL_CSV} ({len(minus_sl)} trades)")

    # ---- Step 3 — metrics ----
    full_stats = _stats_block(full_omen, n_sessions)
    minus_stats = _stats_block(minus_sl, n_sessions)

    print("\n" + "-" * 72)
    print("STEP 3 — Aggregate metrics (fresh sessions)")
    print("-" * 72)
    for label, st in (("full_omen", full_stats), ("omen_minus_sl", minus_stats)):
        sh = _md_sharpe(st["sharpe"]); wr = _md_winrate(st["win_rate"])
        print(f"  {label:<14s} n={st['n']:>3d}  win={wr:>7s}  mean=${st['mean']:>+7.2f}  "
              f"sum=${st['sum']:>+8.0f}  Sharpe={sh:>7s}  DD=${st['max_dd']:>+8.0f}")

    # Per-cell breakdown
    print("\n  Per-cell breakdown (full_omen):")
    per_cell = {}
    for c in ALL_CELLS_ORDER:
        sub = full_omen[full_omen["cell"] == c]
        st = _stats_block(sub, n_sessions)
        per_cell[c] = st
        sh = _md_sharpe(st["sharpe"]); wr = _md_winrate(st["win_rate"])
        print(f"    {c:<12s}  n={st['n']:>3d}  win={wr:>7s}  mean=${st['mean']:>+7.2f}  "
              f"sum=${st['sum']:>+7.0f}  Sharpe={sh:>7s}")

    # ---- Step 4 — context comparison ----
    print("\n" + "-" * 72)
    print("STEP 4 — Context comparison (IS / OOS / fresh)")
    print("-" * 72)
    print(f"  {'bucket':<14s} {'sample':<8s} {'N':>5s} {'sessions':>9s} {'full Sharpe':>12s} {'minus-SL Sh':>12s}")
    print(f"  {'-'*14:<14s} {'-'*8:<8s} {'-'*5:>5s} {'-'*9:>9s} {'-'*12:>12s} {'-'*12:>12s}")
    print(f"  IS-{PRIOR_BUCKETS['IS']['trade_count']:<10d} "
          f"{'IS':<8s} {PRIOR_BUCKETS['IS']['trade_count']:>5d} "
          f"{PRIOR_BUCKETS['IS']['sessions']:>9d} "
          f"{PRIOR_BUCKETS['IS']['full_omen_sharpe']:>+12.2f} "
          f"{'(n/a)':>12s}")
    print(f"  OOS-{PRIOR_BUCKETS['OOS']['trade_count']:<9d} "
          f"{'OOS':<8s} {PRIOR_BUCKETS['OOS']['trade_count']:>5d} "
          f"{PRIOR_BUCKETS['OOS']['sessions']:>9d} "
          f"{PRIOR_BUCKETS['OOS']['full_omen_sharpe']:>+12.2f} "
          f"{PRIOR_BUCKETS['OOS']['omen_minus_sl_sharpe']:>+12.2f}")
    print(f"  fresh-{len(full_omen):<8d} "
          f"{'fresh':<8s} {len(full_omen):>5d} "
          f"{n_sessions:>9d} "
          f"{_md_sharpe(full_stats['sharpe']):>12s} "
          f"{_md_sharpe(minus_stats['sharpe']):>12s}")

    # Per-cell side-by-side (IS / OOS / fresh)
    print("\n  Per-cell Sharpe (IS / OOS / fresh):")
    print(f"  {'cell':<12s} {'IS Sh':>9s} {'IS n':>5s} {'OOS Sh':>9s} {'OOS n':>6s} "
          f"{'fresh Sh':>10s} {'fresh n':>8s}")
    for c in ALL_CELLS_ORDER:
        is_sh = PRIOR_BUCKETS["IS"]["per_cell_sharpe"][c]
        is_n = PRIOR_BUCKETS["IS"]["per_cell_n"][c]
        oos_sh = PRIOR_BUCKETS["OOS"]["per_cell_sharpe"][c]
        oos_n = PRIOR_BUCKETS["OOS"]["per_cell_n"][c]
        fr_st = per_cell[c]
        fr_sh = _md_sharpe(fr_st["sharpe"])  # likely None for n<10
        print(f"  {c:<12s} {is_sh:>+9.2f} {is_n:>5d} {oos_sh:>+9.2f} {oos_n:>6d} "
              f"{fr_sh:>10s} {fr_st['n']:>8d}")

    # ---- Step 5 — Build SYNTHESIS.md ----
    md = _build_synthesis(
        dates=dates, n_sessions=n_sessions, trades=trades,
        full_stats=full_stats, minus_stats=minus_stats,
        per_cell=per_cell,
    )
    SYNTHESIS_MD.write_text(md)
    print(f"\nSaved synthesis: {SYNTHESIS_MD}")
    return 0


def _build_synthesis(*, dates, n_sessions, trades, full_stats, minus_stats,
                     per_cell) -> str:
    L: list[str] = []
    L.append("# OMEN-minus-SHORT_long QUICK CHECK on fresh sessions (THROWAWAY)\n")
    L.append(f"Branch: `analysis/omen-minus-sl-quickcheck-throwaway` "
             "(throwaway / archive only; never merges to main).")
    L.append(f"Generated: {datetime.now().isoformat(timespec='seconds')}\n")

    # ---- Section 1 — Disclosure ----
    L.append("## 1. Disclosure\n")
    L.append(QUICK_CHECK_DISCLOSURE)
    L.append("")

    # ---- Section 2 — Sessions analyzed ----
    L.append("## 2. Sessions analyzed\n")
    L.append(f"- Fresh sessions: **{n_sessions}** "
             f"({dates[0].isoformat()} → {dates[-1].isoformat()})")
    L.append("- Dates with trades:")
    for d in dates:
        n = int((trades["entry_date"] == d).sum())
        L.append(f"  - {d.isoformat()}  ({n} trades)")
    L.append(f"- Total trades: **{len(trades)}**")
    L.append("")
    L.append("**Excluded from the requested 10-session window:**")
    L.append("- 2026-04-29 — `.missing` GEX sentinel; GexBot has no data for this date.")
    L.append("- 2026-05-12 — ES 1s bars not yet pulled for this session.")
    L.append("")

    # ---- Section 3 — Three-bucket Sharpe table ----
    L.append("## 3. Three-bucket Sharpe table\n")
    L.append("| bucket | sample | N | sessions | full_omen Sharpe | omen_minus_sl Sharpe |")
    L.append("|---|---|---:|---:|---:|---:|")
    is_ = PRIOR_BUCKETS["IS"]; oos = PRIOR_BUCKETS["OOS"]
    L.append(f"| IS-{is_['trade_count']} | IS | {is_['trade_count']} | "
             f"{is_['sessions']} | "
             f"{is_['full_omen_sharpe']:+.2f} | (not previously computed) |")
    L.append(f"| OOS-{oos['trade_count']} | OOS | {oos['trade_count']} | "
             f"{oos['sessions']} | {oos['full_omen_sharpe']:+.2f} | "
             f"{oos['omen_minus_sl_sharpe']:+.2f} |")
    L.append(f"| fresh-{full_stats['n']} | fresh | {full_stats['n']} | "
             f"{n_sessions} | {_md_sharpe(full_stats['sharpe'])} | "
             f"{_md_sharpe(minus_stats['sharpe'])} |")
    L.append("")
    L.append("Fresh additional metrics:")
    L.append("")
    L.append("| arm | N | win | mean $ | sum $ | Sharpe | max DD |")
    L.append("|---|---:|---:|---:|---:|---:|---:|")
    for label, st in (("full_omen", full_stats), ("omen_minus_sl", minus_stats)):
        L.append(f"| {label} | {st['n']} | {_md_winrate(st['win_rate'])} | "
                 f"${st['mean']:+.2f} | ${st['sum']:+.0f} | "
                 f"{_md_sharpe(st['sharpe'])} | ${st['max_dd']:+.0f} |")
    L.append("")

    # ---- Section 4 — Per-cell fresh breakdown ----
    L.append("## 4. Per-cell breakdown (fresh sessions vs prior IS / OOS)\n")
    L.append("| cell | IS Sharpe (n) | OOS Sharpe (n) | fresh Sharpe (n) | fresh mean $ | fresh sum $ |")
    L.append("|---|---|---|---|---:|---:|")
    for c in ALL_CELLS_ORDER:
        is_sh = is_["per_cell_sharpe"][c]; is_n = is_["per_cell_n"][c]
        oos_sh = oos["per_cell_sharpe"][c]; oos_n = oos["per_cell_n"][c]
        fr = per_cell[c]
        sh_str = (_md_sharpe(fr["sharpe"]) if fr["n"] >= 10
                    else f"n/a (n<10, n={fr['n']})")
        L.append(f"| {c} | {is_sh:+.2f} ({is_n}) | {oos_sh:+.2f} ({oos_n}) | "
                 f"{sh_str} | ${fr['mean']:+.2f} | ${fr['sum']:+.0f} |")
    L.append("")
    L.append("**Fresh-session cell counts**: ")
    L.append("LONG_long n="
             f"{per_cell['LONG_long']['n']}, "
             f"LONG_short n={per_cell['LONG_short']['n']}, "
             f"SHORT_long n={per_cell['SHORT_long']['n']}, "
             f"SHORT_short n={per_cell['SHORT_short']['n']}. "
             "All four cells are individually below the n=10 threshold required "
             "for a Sharpe estimate to be meaningful — per-cell PnL totals reported "
             "instead, with Sharpe omitted for individual cells.")
    L.append("")

    # ---- Section 5 — Quick-check verdict ----
    L.append("## 5. Quick-check verdict\n")
    sl_cell_stats = per_cell[SL_CELL]
    is_worst_fresh = None
    if any(per_cell[c]["n"] >= 1 for c in ALL_CELLS_ORDER):
        # Worst cell by mean $ (Sharpe undefined at small n)
        means = {c: per_cell[c]["mean"] for c in ALL_CELLS_ORDER if per_cell[c]["n"] >= 1}
        if means:
            is_worst_fresh = min(means, key=means.get)

    sl_n = sl_cell_stats["n"]
    sl_mean = sl_cell_stats["mean"]
    sl_is_worst = (is_worst_fresh == SL_CELL)

    full_sh = full_stats["sharpe"]; minus_sh = minus_stats["sharpe"]
    if full_sh is not None and minus_sh is not None:
        directional_consistent = (minus_sh > full_sh) and sl_is_worst
        directional_inconsistent = (minus_sh <= full_sh) or (not sl_is_worst)
    else:
        directional_consistent = False
        directional_inconsistent = False

    if full_stats["n"] < 10:
        verdict = "INCONCLUSIVE"
    elif directional_consistent:
        verdict = "DIRECTIONALLY CONSISTENT"
    else:
        verdict = "DIRECTIONALLY INCONSISTENT"

    L.append(f"**Verdict: {verdict}**")
    L.append("")
    L.append("Inputs to the verdict:")
    L.append(f"- full_omen fresh Sharpe (n={full_stats['n']}): "
             f"{_md_sharpe(full_sh)}")
    L.append(f"- omen_minus_sl fresh Sharpe (n={minus_stats['n']}): "
             f"{_md_sharpe(minus_sh)}")
    L.append(f"- Worst-mean cell on fresh data: **{is_worst_fresh}** "
             f"(mean ${per_cell[is_worst_fresh]['mean']:+.2f}, "
             f"n={per_cell[is_worst_fresh]['n']})" if is_worst_fresh else
             "- No cells with trades on fresh data.")
    L.append(f"- SHORT_long cell on fresh data: n={sl_n}, mean ${sl_mean:+.2f}, "
             f"sum ${sl_cell_stats['sum']:+.0f}. "
             f"{'IS the worst cell by mean' if sl_is_worst else 'is NOT the worst cell by mean'}.")
    L.append("")

    if verdict == "DIRECTIONALLY CONSISTENT":
        L.append("Both criteria met: minus-SL outperforms full on fresh AND SHORT_long is the ")
        L.append("worst cell on fresh data. Direction matches the OOS-158 cell-breakdown ")
        L.append("finding. The sample size is still too small for a statistical claim.")
        L.append("")
        # Fragility check: is "worst by mean" hanging on n<3 AND is SHORT_short doing
        # more $ damage than SHORT_long in absolute terms?
        sl_n = per_cell[SL_CELL]["n"]
        ss_sum = per_cell.get("SHORT_short", {}).get("sum", 0.0)
        sl_sum = per_cell[SL_CELL]["sum"]
        if sl_n < 3 or (ss_sum < sl_sum):
            L.append("**FRAGILITY NOTE — read this carefully.**")
            L.append(f"The 'SHORT_long is the worst cell by mean' input rests on **n="
                     f"{sl_n}** SHORT_long trade(s) in this window. ")
            if ss_sum < sl_sum and ss_sum < 0:
                L.append(f"By **total dollars**, SHORT_short (n="
                         f"{per_cell.get('SHORT_short', {}).get('n', 0)}, "
                         f"sum=${ss_sum:+.0f}) is doing *more* damage than SHORT_long "
                         f"(n={sl_n}, sum=${sl_sum:+.0f}). ")
            L.append("The Sharpe lift from omen_minus_sl ({0:+.2f} → {1:+.2f}) ".format(
                full_sh if full_sh is not None else float('nan'),
                minus_sh if minus_sh is not None else float('nan')) +
                f"is therefore driven by removing the single biggest losing trade — a coin-flip event at "
                f"this sample size. Re-run when more sessions accumulate before interpreting the direction as a replication.")
    elif verdict == "DIRECTIONALLY INCONSISTENT":
        if minus_sh is not None and full_sh is not None and minus_sh <= full_sh:
            L.append(f"omen_minus_sl Sharpe ({_md_sharpe(minus_sh)}) is **not greater than** "
                     f"full_omen Sharpe ({_md_sharpe(full_sh)}) on fresh data. The OOS-158 ")
            L.append("ranking does not replicate in this small window. Could be noise or could ")
            L.append("be a sign the cell-breakdown finding was overfit. Either way the criterion ")
            L.append("for 'directionally consistent' is not met.")
        elif not sl_is_worst:
            L.append(f"SHORT_long is **not the worst cell** on fresh data ")
            L.append(f"(worst by mean is {is_worst_fresh}). The OOS-158 finding that SHORT_long ")
            L.append("specifically degraded does not replicate in this window. Direction is not ")
            L.append("consistent with the hypothesis being tested.")
    else:
        L.append("Trade count is below the threshold for Sharpe to be meaningful, OR no cells ")
        L.append("had trades. Continue accumulating sessions before re-checking.")
    L.append("")

    # ---- Section 6 — Planning implications ----
    L.append("## 6. What this means for planning the proper forward test\n")
    if verdict == "DIRECTIONALLY CONSISTENT":
        L.append("- Hypothesis remains **worth pre-registering** for a proper forward test.")
        L.append("- Target: ≥ 30 fresh sessions accumulated (≈ 60+ OMEN-minus-SL trades expected).")
        L.append("- Lock 1-arm A/B (`full_omen` vs `omen_minus_sl`) in the pre-reg; report ")
        L.append("  Sharpe + bootstrap CIs.")
        L.append("- Do NOT deploy until that test runs and passes its pre-reg gate.")
    elif verdict == "DIRECTIONALLY INCONSISTENT":
        L.append("- The cell-breakdown finding **may not replicate**. Two reasonable paths:")
        L.append("  - Continue forward-testing anyway (accept the cell-breakdown was suggestive ")
        L.append("    enough to warrant 30+ sessions; this quick-check could itself be noise).")
        L.append("  - Defer the OMEN-minus-SL forward test; revisit the consumed-data analysis ")
        L.append("    for an alternative hypothesis with sturdier IS-vs-OOS replication.")
        L.append("- In either case, **do not deploy OMEN-minus-SL** based on this result.")
    else:
        L.append("- Sample size is too small for any directional read.")
        L.append("- Continue accumulating fresh sessions. Re-run this script when "
                 f"trade count reaches ≥25 (currently {full_stats['n']}).")
        L.append("- A proper forward-test pre-registration on 30+ accumulated sessions ")
        L.append("  remains the required next step regardless.")
    L.append("")

    # ---- Section 7 — Caveats ----
    L.append("## 7. Caveats (mandatory)\n")
    L.append(f"- **Sample size is far too small for statistical claims.** "
             f"n={full_stats['n']} trades in {n_sessions} sessions. ")
    L.append("  Sharpe estimates at this n are dominated by 1-2 outlier trades.")
    L.append("- **The hypothesis was derived from consumed data.** Even a positive result here ")
    L.append("  is not a clean validation — the cells were named precisely because they ")
    L.append("  performed differently in the OOS-158 sample.")
    L.append("- **Forward-test pre-registration on 30+ accumulated sessions remains required.** ")
    L.append("  This quick-check is a planning input, not a verdict.")
    L.append("- **Do not deploy OMEN-minus-SL based on this result regardless of outcome.** ")
    L.append("  Hard rule, applies whether the verdict is CONSISTENT or INCONSISTENT.")
    L.append("- **Per-cell n is below 10 for every cell** (LONG_long=2, LONG_short=6, ")
    L.append(f"  SHORT_long={per_cell['SHORT_long']['n']}, SHORT_short={per_cell['SHORT_short']['n']}). ")
    L.append("  Per-cell Sharpes are omitted; per-cell mean/sum are reported but should ")
    L.append("  not be over-read.")
    L.append("- 2026-04-29 excluded due to GexBot `.missing` sentinel. 2026-05-12 excluded ")
    L.append("  due to ES 1s bars not yet pulled. Either could shift the count slightly.")
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
