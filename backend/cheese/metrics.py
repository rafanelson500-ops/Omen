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

    # Daily Sharpe. Build the per-session PnL series by taking the LAST equity
    # value on each RTH trading day and diffing. We must NOT drop zero-PnL
    # days -- a day with no trades contributes 0 to the numerator and also
    # shrinks volatility in the denominator, which is the statistically
    # correct behavior. The previous implementation filtered `daily != 0`,
    # which systematically inflated Sharpe by only scoring "active" days.
    daily = equity.resample("1D").last().ffill().diff().dropna()
    sharpe = (daily.mean() / daily.std(ddof=0) * np.sqrt(252)) \
        if len(daily) > 1 and daily.std(ddof=0) > 0 else 0.0

    dd = _max_drawdown(equity)
    total = float(net.sum())
    ann_ret = total * (252 / max(1, _trading_days(equity)))

    robustness = robustness_metrics(trades)

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
        "mc_drawdown_95": robustness["mc_drawdown_95"],
        "p_value": robustness["p_value"],
        "robustness_label": robustness["robustness_label"],
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


def robustness_metrics(trades: pd.DataFrame, n_iter: int = 5000) -> dict:
    """Run Monte Carlo and permutation tests on the trade sequence. Returns a dict of metrics and a label."""
    if trades.empty or len(trades) < 10:
        return {
            "mc_drawdown_95": 0.0,
            "p_value": 1.0,
            "robustness_label": "Noisy (Not enough data)"
        }
        
    net = trades["net_dollars"].values
    actual_pnl = net.sum()
    
    # 1. Monte Carlo Drawdown
    # Sample trades with replacement, compute equity curve, record max drawdown.
    # We do this n_iter times to find the 95th percentile worst drawdown.
    mc_dds = np.zeros(n_iter)
    for i in range(n_iter):
        sim_net = np.random.choice(net, size=len(net), replace=True)
        sim_eq = np.cumsum(sim_net)
        peak = np.maximum.accumulate(sim_eq)
        dd = np.min(sim_eq - peak) # drawdown is negative or 0
        mc_dds[i] = dd
        
    mc_dd_95 = np.percentile(mc_dds, 5) # 5th percentile (most negative)
    
    # 2. Permutation Test (Bootstrap p-value for mean > 0)
    # Null hypothesis: The strategy has zero edge (mean PnL = 0).
    # We center the trades so their mean is exactly 0, then sample with replacement.
    # What fraction of these null-hypothesis trajectories achieve the actual PnL?
    centered_net = net - np.mean(net)
    null_sums = np.zeros(n_iter)
    for i in range(n_iter):
        sim_null = np.random.choice(centered_net, size=len(net), replace=True)
        null_sums[i] = np.sum(sim_null)
        
    p_value = np.mean(null_sums >= actual_pnl)
    
    # 3. Simple Labels
    # Combine the p-value and MC drawdown risk into human-readable labels
    if actual_pnl <= 0:
        label = "Unprofitable"
    elif p_value < 0.05:
        # Statistically significant edge
        if abs(mc_dd_95) > abs(actual_pnl):
            label = "Risky (High MC Drawdown)"
        else:
            label = "Robust"
    elif p_value < 0.15:
        # Borderline significance
        if abs(mc_dd_95) > abs(actual_pnl):
            label = "Average / Risky"
        else:
            label = "Promising"
    else:
        label = "Noisy"
        
    return {
        "mc_drawdown_95": float(mc_dd_95),
        "p_value": float(p_value),
        "robustness_label": label
    }


def _trades_by_day(trades: pd.DataFrame) -> list[np.ndarray]:
    """Group trade PnLs by trading day, preserving intraday order."""
    if trades.empty:
        return []
    df = trades.copy()
    df["_day"] = pd.to_datetime(df["entry_time"]).dt.date
    df = df.sort_values("entry_time")
    return [grp["net_dollars"].values for _, grp in df.groupby("_day", sort=True)]


def daily_block_bootstrap(
    trades: pd.DataFrame,
    n_iter: int = 2000,
    n_days: int | None = None,
) -> dict:
    """Daily-block bootstrap: sample whole days (with replacement) to preserve
    intraday clustering, day-of-week effects, and within-day autocorrelation.
    
    Returns simulated paths (each path is a sequence of cumulative PnL across days),
    plus distributions for final return, max drawdown, and per-trade EV.
    """
    day_groups = _trades_by_day(trades)
    if not day_groups:
        return {
            "paths": np.zeros((0, 0)),
            "final_returns": np.zeros(0),
            "max_drawdowns": np.zeros(0),
            "ev_per_trade": np.zeros(0),
            "trade_paths": np.zeros((0, 0)),
        }

    n_days_total = len(day_groups)
    n_days = n_days or n_days_total
    
    # We pick n_days random days (with replacement). For each draw we paste in
    # that day's full PnL sequence. The "path" is the cumulative equity at
    # end-of-day boundaries. trade_paths is the bar-by-bar (trade-by-trade)
    # cumulative path needed for the prop firm intraday barrier check.
    paths_eod = np.zeros((n_iter, n_days))
    final_returns = np.zeros(n_iter)
    max_drawdowns = np.zeros(n_iter)
    ev_per_trade = np.zeros(n_iter)

    # Precompute day sums for quicker EOD path building
    day_sums = np.array([float(g.sum()) for g in day_groups])
    
    # Trade-level paths are variable-length per iter; keep as list-of-arrays.
    # Caller can pad later if it wants a 2D matrix.
    trade_paths_list: list[np.ndarray] = []

    rng = np.random.default_rng()
    for i in range(n_iter):
        idx = rng.integers(0, n_days_total, size=n_days)
        # EOD path
        eod_pnls = day_sums[idx]
        eq_eod = np.cumsum(eod_pnls)
        paths_eod[i] = eq_eod
        final_returns[i] = eq_eod[-1]
        peak_eod = np.maximum.accumulate(eq_eod)
        max_drawdowns[i] = float(np.min(eq_eod - peak_eod))
        # Trade-level path
        chunks = [day_groups[j] for j in idx]
        trade_seq = np.concatenate(chunks) if chunks else np.array([])
        ev_per_trade[i] = float(trade_seq.mean()) if trade_seq.size else 0.0
        trade_paths_list.append(np.cumsum(trade_seq))

    # Pad trade paths to a 2D matrix for plotting (NaN-padded right side)
    max_len = max((len(p) for p in trade_paths_list), default=0)
    trade_paths = np.full((n_iter, max_len), np.nan)
    for i, p in enumerate(trade_paths_list):
        trade_paths[i, : len(p)] = p

    return {
        "paths": paths_eod,
        "final_returns": final_returns,
        "max_drawdowns": max_drawdowns,
        "ev_per_trade": ev_per_trade,
        "trade_paths": trade_paths,
        "day_groups": day_groups,
    }


def prop_firm_simulation(
    trades: pd.DataFrame,
    profit_target: float = 3000.0,
    drawdown_limit: float = 2500.0,
    trailing_mode: str = "eod",
    n_iter: int = 2000,
    n_days: int | None = None,
) -> dict:
    """Simulate a prop firm double-barrier challenge using daily-block bootstrap.
    
    Each iteration draws a random sequence of trading days. We walk forward
    trade-by-trade and stop the simulation as soon as either:
        - cumulative equity >= profit_target  -> "pass"
        - cumulative equity <= trailing_min   -> "fail"
        - all days exhausted with no touch    -> "timeout"
    
    The lower barrier is a drawdown limit with three modes (trailing_mode):
        - "eod": the high-water mark only updates at the close
          of each day. Intraday equity above the prior HWM does NOT raise
          the barrier (typical Topstep/Apex style end-of-day-trail).
        - "instant": HWM updates instantly on every trade.
        - "static": HWM never updates. Lower barrier is fixed at -drawdown_limit.
    
    The lower barrier trails the HWM upward indefinitely (no lock at start).
    
    Returns counts of pass/fail/timeout outcomes plus the equity paths so
    we can plot a "spaghetti chart" of N sample runs.
    """
    day_groups = _trades_by_day(trades)
    if not day_groups:
        return {
            "outcomes": {"pass": 0, "fail": 0, "timeout": 0},
            "pass_rate": 0.0,
            "fail_rate": 0.0,
            "timeout_rate": 0.0,
            "median_days_to_outcome": 0.0,
            "sample_paths": [],
            "sample_outcomes": [],
        }

    n_days_total = len(day_groups)
    n_days = n_days or n_days_total

    rng = np.random.default_rng()
    outcomes = {"pass": 0, "fail": 0, "timeout": 0}
    days_to_outcome: list[int] = []
    sample_paths: list[np.ndarray] = []
    sample_outcomes: list[str] = []
    sample_target = min(200, n_iter)  # keep at most 200 paths for plotting

    for i in range(n_iter):
        idx = rng.integers(0, n_days_total, size=n_days)
        eq = 0.0
        hwm = 0.0
        trailing_min = -drawdown_limit
        outcome: str | None = None
        path = [0.0]
        day_count = 0

        for day_i, j in enumerate(idx):
            day_pnl_seq = day_groups[j]
            for trade_pnl in day_pnl_seq:
                eq += float(trade_pnl)
                if trailing_mode == "instant":
                    if eq > hwm:
                        hwm = eq
                        trailing_min = hwm - drawdown_limit
                path.append(eq)
                if eq >= profit_target:
                    outcome = "pass"
                    break
                if eq <= trailing_min:
                    outcome = "fail"
                    break
            day_count = day_i + 1
            if outcome is not None:
                break
            if trailing_mode == "eod":
                if eq > hwm:
                    hwm = eq
                    trailing_min = hwm - drawdown_limit

        if outcome is None:
            outcome = "timeout"
        outcomes[outcome] += 1
        days_to_outcome.append(day_count)
        if i < sample_target:
            sample_paths.append(np.asarray(path, dtype="float64"))
            sample_outcomes.append(outcome)

    total = max(1, n_iter)
    return {
        "outcomes": outcomes,
        "pass_rate": outcomes["pass"] / total,
        "fail_rate": outcomes["fail"] / total,
        "timeout_rate": outcomes["timeout"] / total,
        "median_days_to_outcome": float(np.median(days_to_outcome)) if days_to_outcome else 0.0,
        "sample_paths": sample_paths,
        "sample_outcomes": sample_outcomes,
    }


def _empty_summary() -> dict:
    keys = ["trades", "win_rate", "avg_win", "avg_loss", "expectancy",
            "profit_factor", "total_pnl", "total_cost", "sharpe_daily",
            "max_drawdown", "avg_bars_held", "ann_pnl_est", 
            "mc_drawdown_95", "p_value"]
    return {k: 0.0 for k in keys} | {"trades": 0, "robustness_label": "Noisy (Not enough data)"}
