"""Performance metrics: headline stats, per-regime, per-exit-reason."""
from __future__ import annotations

import numpy as np
import pandas as pd


def summarize(trades: pd.DataFrame, equity: pd.Series) -> dict:
    """Headline summary of a backtest run. Returns a dict of scalars."""
    if trades.empty:
        return _empty_summary()

    net = trades["net_dollars"]
    wins = net[net > 0]
    losses = net[net <= 0]
    n = len(net)

    # Session-level sharpe (daily)
    daily = equity.resample("1D").last().diff().dropna()
    daily = daily[daily != 0]
    sharpe = (daily.mean() / daily.std(ddof=0) * np.sqrt(252)) if len(daily) > 1 and daily.std() > 0 else 0.0

    dd = _max_drawdown(equity)
    total = float(net.sum())
    ndays = max(1, (equity.index[-1].date() - equity.index[0].date()).days)
    ann_ret = total * (252 / max(1, _trading_days(equity)))

    return {
        "trades": int(n),
        "win_rate": float((net > 0).mean()),
        "avg_win": float(wins.mean()) if len(wins) else 0.0,
        "avg_loss": float(losses.mean()) if len(losses) else 0.0,
        "expectancy": float(net.mean()),
        "profit_factor": float(wins.sum() / abs(losses.sum())) if losses.sum() < 0 else float("inf"),
        "total_pnl": total,
        "total_cost": float(trades["cost_dollars"].sum()),
        "sharpe_daily": float(sharpe),
        "max_drawdown": float(dd),
        "avg_bars_held": float(trades["bars_held"].mean()),
        "ann_pnl_est": float(ann_ret),
    }


def regime_breakdown(trades: pd.DataFrame) -> pd.DataFrame:
    if trades.empty or "gamma_regime" not in trades.columns:
        return pd.DataFrame()
    g = trades.groupby("gamma_regime")["net_dollars"]
    return pd.DataFrame({
        "trades": g.count(),
        "win_rate": trades.groupby("gamma_regime").apply(lambda d: (d["net_dollars"] > 0).mean()),
        "expectancy": g.mean(),
        "total": g.sum(),
    }).reset_index()


def exit_reason_breakdown(trades: pd.DataFrame) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame()
    g = trades.groupby("exit_reason")["net_dollars"]
    return pd.DataFrame({
        "trades": g.count(),
        "expectancy": g.mean(),
        "total": g.sum(),
    }).reset_index()


def per_day_pnl(equity: pd.Series) -> pd.Series:
    if equity.empty:
        return pd.Series(dtype="float64")
    return equity.resample("1D").last().diff().dropna()


def _max_drawdown(equity: pd.Series) -> float:
    if equity.empty:
        return 0.0
    peak = equity.cummax()
    dd = equity - peak
    return float(dd.min())


def _trading_days(equity: pd.Series) -> int:
    if equity.empty:
        return 0
    return equity.resample("1D").last().dropna().index.nunique()


def _empty_summary() -> dict:
    keys = ["trades", "win_rate", "avg_win", "avg_loss", "expectancy",
            "profit_factor", "total_pnl", "total_cost", "sharpe_daily",
            "max_drawdown", "avg_bars_held", "ann_pnl_est"]
    return {k: 0.0 for k in keys} | {"trades": 0}
