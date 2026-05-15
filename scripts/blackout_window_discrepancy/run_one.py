"""Run a single backtest of the locked OMEN baseline on the IS corpus,
attach cell labels (side x gamma_regime), and dump trade detail + metrics.

Invoked twice from compare.py:
  - Run A: locked code (blackout 10:30-12:30)
  - Run B: strategy.py temporarily edited to 12:00-13:00

The pipeline call is identical for both; the only variable is whatever
strategy.py:58 happens to contain at the moment of import.

Outputs (under diagnostics/blackout-window-discrepancy/):
  trades_<label>.csv  - one row per trade with cell label
  metrics_<label>.json - headline metrics + per-cell + exit distribution
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path("/Users/rafanelson/Omen")
sys.path.insert(0, str(REPO / "backend"))

from cheese import backtest, features, gex, market, strategy  # noqa: E402
from cheese.config import BacktestConfig  # noqa: E402

OUT_DIR = REPO / "diagnostics" / "blackout-window-discrepancy"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Locked OMEN baseline params (mirrors all-bugfixes-baseline / forward-test pre-reg)
Z_THRESHOLD = 1.8
BAR_FREQ = "5min"
BLACKOUT_LUNCH = True

# IS corpus per spec
IS_START = dt.date(2025, 12, 26)
IS_END = dt.date(2026, 4, 22)


def _attach_cell(trades: pd.DataFrame) -> pd.DataFrame:
    if trades.empty:
        return trades
    side_label = np.where(trades["side"] == 1, "LONG", "SHORT")
    cell = side_label + "_" + trades["gamma_regime"].astype(str)
    out = trades.copy()
    out["side_label"] = side_label
    out["cell"] = cell
    return out


def _daily_sharpe(equity: pd.Series) -> float:
    if equity.empty:
        return 0.0
    daily = equity.resample("1D").last().ffill().diff().dropna()
    if len(daily) <= 1 or daily.std(ddof=0) == 0:
        return 0.0
    return float(daily.mean() / daily.std(ddof=0) * np.sqrt(252))


def _max_dd(equity: pd.Series) -> float:
    if equity.empty:
        return 0.0
    peak = equity.cummax()
    return float((equity - peak).min())


def _headline(trades: pd.DataFrame, equity: pd.Series) -> dict:
    n = int(len(trades))
    if n == 0:
        return {"trades": 0, "total_pnl": 0.0, "win_rate": None,
                "mean_pnl": 0.0, "avg_win": None, "avg_loss": None,
                "profit_factor": None, "sharpe_daily": 0.0, "max_dd": 0.0}
    net = trades["net_dollars"]
    wins = net[net > 0]
    losses = net[net <= 0]
    pf = (float(wins.sum() / abs(losses.sum()))
          if losses.sum() < 0 else None)
    return {
        "trades": n,
        "total_pnl": float(net.sum()),
        "win_rate": float((net > 0).mean()),
        "mean_pnl": float(net.mean()),
        "avg_win": float(wins.mean()) if len(wins) else None,
        "avg_loss": float(losses.mean()) if len(losses) else None,
        "profit_factor": pf,
        "sharpe_daily": _daily_sharpe(equity),
        "max_dd": _max_dd(equity),
    }


def _per_cell(trades: pd.DataFrame) -> list[dict]:
    cells = ["LONG_long", "LONG_short", "SHORT_long", "SHORT_short"]
    out = []
    for c in cells:
        sub = trades[trades["cell"] == c] if not trades.empty else trades
        if len(sub) == 0:
            out.append({"cell": c, "n": 0, "total_pnl": 0.0, "win_rate": None})
            continue
        out.append({
            "cell": c,
            "n": int(len(sub)),
            "total_pnl": float(sub["net_dollars"].sum()),
            "win_rate": float((sub["net_dollars"] > 0).mean()),
        })
    return out


def _exit_dist(trades: pd.DataFrame) -> dict:
    if trades.empty:
        return {}
    return trades["exit_reason"].value_counts().to_dict()


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--label", required=True, help="e.g. 'A_locked' or 'B_doc_window'")
    args = p.parse_args()

    print(f"[{args.label}] loading market + GEX, building features ...")
    mkt = market.load(IS_START, IS_END, freq=BAR_FREQ, rth_only=True)
    days = gex.rth_sessions(IS_START, IS_END)
    gex_raw = gex.load_range(days)
    gex_bars = gex.resample(gex_raw, freq=BAR_FREQ)
    feat = features.build_features(mkt, gex_bars)
    print(f"[{args.label}] feature rows={len(feat):,}  sessions={len(days)}")

    cfg = BacktestConfig(bar_freq=BAR_FREQ)
    strat = strategy.FlowBurstStrategy(z_threshold=Z_THRESHOLD,
                                       blackout_lunch=BLACKOUT_LUNCH)
    signals = strat.signals(feat)
    trades, equity = backtest.run(feat, signals,
                                  strategy_name="flow_burst", cfg=cfg)
    trades = _attach_cell(trades)
    print(f"[{args.label}] trades={len(trades)}")

    trades_path = OUT_DIR / f"trades_{args.label}.csv"
    trades.to_csv(trades_path, index=False)
    print(f"[{args.label}] wrote {trades_path}")

    metrics = {
        "label": args.label,
        "is_start": IS_START.isoformat(),
        "is_end": IS_END.isoformat(),
        "n_sessions_in_range": len(days),
        "config": {"z_threshold": Z_THRESHOLD, "bar_freq": BAR_FREQ,
                   "blackout_lunch": BLACKOUT_LUNCH},
        "headline": _headline(trades, equity),
        "per_cell": _per_cell(trades),
        "exit_dist": _exit_dist(trades),
    }
    metrics_path = OUT_DIR / f"metrics_{args.label}.json"
    with open(metrics_path, "w") as f:
        json.dump(metrics, f, indent=2, default=str)
    print(f"[{args.label}] wrote {metrics_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
