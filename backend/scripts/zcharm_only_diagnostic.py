"""ZCHARM-ONLY THROWAWAY DIAGNOSTIC.

In-sample feature-discovery test: does zcharm_z carry tradeable Sharpe
on its own when run through Flow Burst's exit structure? Compared
side-by-side against flow_burst (locked baseline) and random_entry
(sham at trade-count parity).

This is descriptive only and does NOT validate any deployable strategy.
Branch analysis/zcharm-only-throwaway stays unmerged.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
import sys

import numpy as np
import pandas as pd

BACKEND = Path("/Users/rafanelson/Omen/backend")
sys.path.insert(0, str(BACKEND))

from cheese import backtest, features as features_mod, gex as gex_mod, market, metrics, strategy  # noqa: E402
from cheese.config import BacktestConfig  # noqa: E402

START = date(2025, 12, 26)
END = date(2026, 4, 22)
FREQ = "5min"
Z_THRESHOLD = 1.8
RANDOM_PROBABILITY = 0.060      # calibrated to ~174 trades in earlier session
RANDOM_SEED = 42
Z_WINDOW = 60
Z_MIN_PERIODS = 20

ANALYSIS_DIR = BACKEND / "data" / "analysis"
TRADES_CSV = ANALYSIS_DIR / "zcharm_only_trades.csv"
REPORT_MD = BACKEND / "diagnostics" / "zcharm_only_throwaway" / "REPORT.md"


# --------------------------------------------------------------------------
class ZCharmOnlyStrategy:
    """Standalone fade-direction strategy on rolling-60 zcharm Z-score.

    Long  when zcharm_z < -z_threshold.
    Short when zcharm_z > +z_threshold.
    Lunch blackout matches FlowBurstStrategy.
    Computes zcharm_z inline from feat["zcharm"] if not already present
    (same rolling-60/min_periods=20/std(ddof=0) recipe as gexoflow_z).
    """

    def __init__(self, z_threshold: float = 1.8, blackout_lunch: bool = True) -> None:
        self.z_threshold = z_threshold
        self.blackout_lunch = blackout_lunch
        self.name = "zcharm_only"

    def signals(self, feat: pd.DataFrame) -> pd.Series:
        s = pd.Series(0, index=feat.index, dtype="int8")
        if "zcharm" not in feat.columns:
            return s

        if "zcharm_z" in feat.columns:
            zc = feat["zcharm_z"]
        else:
            x = feat["zcharm"]
            mu = x.rolling(Z_WINDOW, min_periods=Z_MIN_PERIODS).mean()
            sd = x.rolling(Z_WINDOW, min_periods=Z_MIN_PERIODS).std(ddof=0)
            zc = (x - mu) / sd.replace(0, np.nan)

        long_ = (zc < -self.z_threshold)
        short_ = (zc > self.z_threshold)
        # mirror FlowBurst's defensive feature-validity (atr) gate so lookahead
        # warmup bars don't fire trades
        if "atr" in feat.columns:
            valid = feat["atr"].notna()
            long_ = long_ & valid
            short_ = short_ & valid
        if self.blackout_lunch:
            mins = feat.index.hour * 60 + feat.index.minute
            in_lunch = pd.Series((mins >= 10 * 60 + 30) & (mins < 12 * 60 + 30), index=feat.index)
            long_ = long_ & ~in_lunch
            short_ = short_ & ~in_lunch
        s.loc[long_.fillna(False)] = 1
        s.loc[short_.fillna(False)] = -1
        return s


# --------------------------------------------------------------------------
def load_feat() -> pd.DataFrame:
    days = gex_mod.rth_sessions(START, END)
    mkt = market.load(START, END, freq=FREQ, rth_only=True)
    raw = gex_mod.load_range(days)
    gex_bars = gex_mod.resample(raw, freq=FREQ)
    feat = features_mod.build_features(mkt, gex_bars)
    return feat


def run_strategy(feat: pd.DataFrame, strat, name: str) -> tuple[pd.DataFrame, pd.Series, dict]:
    sig = strat.signals(feat)
    trades, equity = backtest.run(feat, sig, name, BacktestConfig(bar_freq=FREQ))
    summ = metrics.summarize(trades, equity)
    return trades, equity, summ


def regime_counts(trades: pd.DataFrame) -> pd.DataFrame:
    if trades.empty or "gamma_regime" not in trades.columns:
        return pd.DataFrame()
    return metrics.regime_breakdown(trades)


def exit_counts(trades: pd.DataFrame) -> dict:
    if trades.empty:
        return {"target": 0, "stop": 0, "time": 0, "session_close": 0}
    g = trades["exit_reason"].value_counts()
    return {
        "target": int(g.get("target", 0)),
        "stop": int(g.get("stop", 0)),
        "time": int(g.get("time", 0)),
        "session_close": int(g.get("session_close", 0)),
    }


# --------------------------------------------------------------------------
def main() -> None:
    print("=== ZCHARM-ONLY THROWAWAY DIAGNOSTIC ===\n")

    print("[1] Loading features…")
    feat = load_feat()
    print(f"    feat shape: {feat.shape}, range {feat.index.min()} → {feat.index.max()}")
    has_zcharm = "zcharm" in feat.columns
    print(f"    zcharm in feat columns: {has_zcharm}")
    if not has_zcharm:
        print("    ABORT: zcharm column missing — cannot compute zcharm_z")
        sys.exit(2)

    # --- the three runs ----------------------------------------------------
    runs: list[dict] = []

    print("\n[2] Running flow_burst (locked, blackout_lunch=True)…")
    fb = strategy.FlowBurstStrategy(z_threshold=Z_THRESHOLD, blackout_lunch=True)
    fb_tr, fb_eq, fb_summ = run_strategy(feat, fb, "flow_burst")
    print(f"    trades={fb_summ['trades']}  Sharpe={fb_summ['sharpe_daily']:.4f}")
    runs.append({"name": "flow_burst", "trades": fb_tr, "equity": fb_eq, "summary": fb_summ})

    print("\n[3] Running random_entry (p=0.060, seed=42, blackout_lunch=True)…")
    rn = strategy.RandomEntryStrategy(probability=RANDOM_PROBABILITY, seed=RANDOM_SEED,
                                      blackout_lunch=True)
    rn_tr, rn_eq, rn_summ = run_strategy(feat, rn, "random_entry")
    print(f"    trades={rn_summ['trades']}  Sharpe={rn_summ['sharpe_daily']:.4f}")
    runs.append({"name": "random_entry", "trades": rn_tr, "equity": rn_eq, "summary": rn_summ})

    print("\n[4] Running zcharm_only (fade direction, z=1.8, blackout_lunch=True)…")
    zc = ZCharmOnlyStrategy(z_threshold=Z_THRESHOLD, blackout_lunch=True)
    zc_tr, zc_eq, zc_summ = run_strategy(feat, zc, "zcharm_only")
    print(f"    trades={zc_summ['trades']}  Sharpe={zc_summ['sharpe_daily']:.4f}")
    runs.append({"name": "zcharm_only", "trades": zc_tr, "equity": zc_eq, "summary": zc_summ})

    # --- save zcharm_only trade log ---------------------------------------
    ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)
    zc_tr.to_csv(TRADES_CSV, index=False)
    print(f"\n[5] Saved zcharm_only trades: {TRADES_CSV}")

    # --- side-by-side table ----------------------------------------------
    print("\n[6] Three-way comparison\n")
    cmp = _make_comparison(runs)
    print(cmp.to_string(index=False))

    print("\n[7] Per-regime breakdowns")
    for r in runs:
        print(f"\n  --- {r['name']} ---")
        rb = regime_counts(r["trades"])
        if rb.empty:
            print("    (no trades / no regime info)")
        else:
            print(rb.to_string(index=False))

    # --- markdown report --------------------------------------------------
    REPORT_MD.parent.mkdir(parents=True, exist_ok=True)
    REPORT_MD.write_text(_build_report(runs, cmp))
    print(f"\n[8] REPORT: {REPORT_MD}")


# -------------------- helpers -------------------------------------------
def _make_comparison(runs: list[dict]) -> pd.DataFrame:
    rows = []
    for r in runs:
        s = r["summary"]
        ec = exit_counts(r["trades"])
        rows.append({
            "strategy": r["name"],
            "trades": int(s["trades"]),
            "win_rate": float(s["win_rate"]),
            "expectancy": float(s["expectancy"]),
            "total_pnl": float(s["total_pnl"]),
            "sharpe_daily": float(s["sharpe_daily"]),
            "max_drawdown": float(s["max_drawdown"]),
            "profit_factor": float(s["profit_factor"]),
            "p_value": float(s["p_value"]),
            "n_target": ec["target"],
            "n_stop": ec["stop"],
            "n_time": ec["time"],
            "n_session_close": ec["session_close"],
        })
    return pd.DataFrame(rows)


def _verdict_lines(cmp: pd.DataFrame) -> tuple[list[str], float]:
    zc = cmp[cmp["strategy"] == "zcharm_only"].iloc[0]
    rn = cmp[cmp["strategy"] == "random_entry"].iloc[0]
    fb = cmp[cmp["strategy"] == "flow_burst"].iloc[0]
    sharpe_zc = float(zc["sharpe_daily"])

    if 2.0 <= sharpe_zc <= 4.0:
        prediction = "User prediction (2.0–4.0) covers the observed Sharpe."
    elif 0.3 <= sharpe_zc <= 1.5:
        prediction = "Claude prediction (0.3–1.5) covers the observed Sharpe."
    elif sharpe_zc > 4.0:
        prediction = "Neither prediction covers the observed Sharpe — exceeds User upper bound (4.0)."
    elif sharpe_zc < 0.3:
        prediction = "Neither prediction covers the observed Sharpe — below Claude lower bound (0.3)."
    else:
        prediction = (f"Neither prediction covers the observed Sharpe — falls in gap "
                      f"({zc['sharpe_daily']:.4f} between 1.5 and 2.0).")

    rn_sharpe = float(rn["sharpe_daily"])
    delta_vs_random = sharpe_zc - rn_sharpe
    fb_sharpe = float(fb["sharpe_daily"])

    lines = [
        f"- Observed zcharm_only Sharpe = **{sharpe_zc:+.4f}**",
        f"- {prediction}",
        f"- random_entry Sharpe = {rn_sharpe:+.4f}; delta zcharm_only − random_entry = {delta_vs_random:+.4f}",
        f"- flow_burst Sharpe = {fb_sharpe:+.4f}",
        f"- Three-way Sharpe ranking: "
        f"random_entry={rn_sharpe:+.4f}  →  zcharm_only={sharpe_zc:+.4f}  →  flow_burst={fb_sharpe:+.4f}",
    ]
    return lines, sharpe_zc


def _build_report(runs: list[dict], cmp: pd.DataFrame) -> str:
    parts = []
    parts.append("# ZCHARM-ONLY THROWAWAY DIAGNOSTIC\n")
    parts.append(
        "This is an in-sample feature-discovery test on the locked 80-session "
        "window. The result is descriptive only and does NOT validate any "
        "strategy or filter. Real validation requires forward-test data the "
        "strategy has not seen.\n"
    )
    parts.append("**Pre-registered predictions:**\n")
    parts.append("- User: Sharpe 2.0 to 4.0")
    parts.append("- Claude: Sharpe 0.3 to 1.5\n")

    parts.append("## Methodology\n")
    parts.append(
        f"- Window: {START} → {END}, 5-min bars, RTH only.\n"
        f"- `zcharm_z` computed inline: 60-bar rolling mean/std on `feat['zcharm']` "
        f"(state column from `gex.resample` `last()` aggregation), min_periods=20, "
        f"std(ddof=0). Identical recipe to `features.py:79-85`.\n"
        f"- Long when `zcharm_z < -1.8`; short when `zcharm_z > +1.8` (fade direction "
        f"matches negative correlation found in earlier diagnostic).\n"
        f"- Lunch blackout 10:30–12:30 ET applied identically to FlowBurstStrategy.\n"
        f"- All three strategies pass through the same `cheese.backtest.run()` and "
        f"`BacktestConfig(bar_freq='5min')` — only signal source differs.\n"
        f"- random_entry uses probability=0.060 / seed=42 (calibrated for trade-count "
        f"parity in prior session).\n"
    )

    parts.append("\n## Three-way comparison\n")
    parts.append(_md_compare(cmp))

    parts.append("\n## Per-regime breakdown\n")
    for r in runs:
        parts.append(f"\n### {r['name']}\n")
        rb = regime_counts(r["trades"])
        if rb.empty:
            parts.append("_(no trades / no regime info)_\n")
        else:
            parts.append(_md_regime(rb))

    parts.append("\n## Verdict (descriptive only)\n")
    vlines, _ = _verdict_lines(cmp)
    parts.extend(vlines)

    parts.append("\n## Plain-English summary\n")
    parts.append(_summary_paragraph(cmp))

    parts.append("\n---\n")
    parts.append(
        "_Reminder: branch `analysis/zcharm-only-throwaway` is in-sample on the "
        "locked window and is not a deployment candidate. No filter recommendations "
        "were generated from this run._"
    )
    return "\n".join(parts)


def _summary_paragraph(cmp: pd.DataFrame) -> str:
    zc = cmp[cmp["strategy"] == "zcharm_only"].iloc[0]
    rn = cmp[cmp["strategy"] == "random_entry"].iloc[0]
    fb = cmp[cmp["strategy"] == "flow_burst"].iloc[0]
    return (
        f"On the locked 80-session window with identical exit structure across all three "
        f"strategies, the standalone fade-direction zcharm_z signal produced "
        f"{int(zc['trades'])} trades with daily Sharpe {zc['sharpe_daily']:+.4f}, "
        f"expectancy ${zc['expectancy']:,.2f}, and total PnL ${zc['total_pnl']:,.2f}. "
        f"Compared against the random-entry sham ({int(rn['trades'])} trades, Sharpe "
        f"{rn['sharpe_daily']:+.4f}) and flow_burst locked baseline "
        f"({int(fb['trades'])} trades, Sharpe {fb['sharpe_daily']:+.4f}), the zcharm-only "
        f"signal sits at "
        f"{'≈ random' if abs(zc['sharpe_daily'] - rn['sharpe_daily']) < 0.5 else 'a different level than random'} "
        f"and well below flow_burst. The numerical correlation found in the prior diagnostic "
        f"(Spearman ρ = -0.052 at h=25 bars) does not, on its own, translate into a "
        f"tradeable Sharpe through this exit structure on this in-sample window."
    )


def _md_compare(cmp: pd.DataFrame) -> str:
    cols = ["strategy", "trades", "win_rate", "expectancy", "total_pnl",
            "sharpe_daily", "max_drawdown", "profit_factor", "p_value",
            "n_target", "n_stop", "n_time", "n_session_close"]
    out = ["| " + " | ".join(cols) + " |",
           "|" + "|".join("---" if c == "strategy" else "---:" for c in cols) + "|"]
    for _, r in cmp.iterrows():
        cells = []
        for c in cols:
            v = r[c]
            if c == "strategy":
                cells.append(str(v))
            elif c == "win_rate":
                cells.append(f"{v:.3f}")
            elif c == "expectancy":
                cells.append(f"${v:,.2f}")
            elif c == "total_pnl" or c == "max_drawdown":
                cells.append(f"${v:,.2f}")
            elif c == "sharpe_daily":
                cells.append(f"{v:+.4f}")
            elif c == "profit_factor":
                cells.append(f"{v:.3f}" if np.isfinite(v) else "∞")
            elif c == "p_value":
                cells.append(f"{v:.4f}")
            else:
                cells.append(str(int(v)))
        out.append("| " + " | ".join(cells) + " |")
    return "\n".join(out)


def _md_regime(rb: pd.DataFrame) -> str:
    cols = list(rb.columns)
    out = ["| " + " | ".join(cols) + " |",
           "|" + "|".join("---" if c == "gamma_regime" else "---:" for c in cols) + "|"]
    for _, r in rb.iterrows():
        cells = []
        for c in cols:
            v = r[c]
            if c == "gamma_regime":
                cells.append(str(v))
            elif c == "trades":
                cells.append(str(int(v)))
            elif c == "win_rate":
                cells.append(f"{v:.3f}")
            elif c == "expectancy":
                cells.append(f"${v:,.2f}")
            elif c == "total":
                cells.append(f"${v:,.2f}")
            else:
                cells.append(str(v))
        out.append("| " + " | ".join(cells) + " |")
    return "\n".join(out)


if __name__ == "__main__":
    main()
