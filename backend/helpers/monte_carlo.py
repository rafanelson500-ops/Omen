import numpy as np
import pandas as pd
from numba import jit
import time

ruin_threshold = -150
success_threshold = 300

@jit(nopython=True)
def calculate_max_drawdown(cumulative_returns):
    """Calculate maximum drawdown from cumulative returns."""
    n = len(cumulative_returns)
    if n == 0:
        return 0.0
    
    peak = cumulative_returns[0]
    max_dd = 0.0
    
    for i in range(1, n):
        if cumulative_returns[i] > peak:
            peak = cumulative_returns[i]
        drawdown = peak - cumulative_returns[i]
        if drawdown > max_dd:
            max_dd = drawdown
    
    return max_dd

@jit(nopython=True)
def block_bootstrap_trades(trade_returns, num_trades, block_starts, block_size):
    """
    Block bootstrap sample trades with replacement.

    Samples consecutive blocks (sequences) of trades instead of individual trades,
    preserving the local autocorrelation structure within trade sequences.

    Args:
        trade_returns: Array of actual trade returns
        num_trades:    Number of trades to produce
        block_starts:  Pre-generated array of random block start indices
        block_size:    Number of consecutive trades per block

    Returns:
        Array of sampled trade returns of length num_trades
    """
    n_trades = len(trade_returns)
    max_start = n_trades - block_size  # last valid start position

    sampled = np.zeros(num_trades, dtype=np.float64)

    if max_start < 0:
        # Fewer trades than block_size — fall back to cycling the available trades
        for i in range(num_trades):
            sampled[i] = trade_returns[i % n_trades]
        return sampled

    pos = 0
    block_idx = 0
    while pos < num_trades:
        start = block_starts[block_idx % len(block_starts)] % (max_start + 1)
        for j in range(block_size):
            if pos >= num_trades:
                break
            sampled[pos] = trade_returns[start + j]
            pos += 1
        block_idx += 1

    return sampled

@jit(nopython=True)
def classify_outcome(equity_curve, s_thresh, r_thresh):
    """
    Walk the equity curve and classify the simulation into exactly one of three
    mutually-exclusive outcomes (so probabilities always sum to 1.0):

        1.0  — success_threshold touched first
       -1.0  — trailing ruin touched first
        0.0  — neither threshold was touched

    Ruin is a TRAILING drawdown (prop-firm style):
        ruin_level = peak + r_thresh   (e.g. peak - 150)
    The ruin level rises with every new equity peak, but never falls.
    Success is a FIXED absolute level (s_thresh, e.g. +300).

    Example: equity rises to +200, then ruin_level = 200 - 150 = +50.
             If equity then drops to +50 or below, ruin is triggered.

    Args:
        equity_curve: Cumulative equity array (starting from 0)
        s_thresh:     Fixed success threshold  (e.g. +300)
        r_thresh:     Drawdown magnitude as a negative number (e.g. -150)
    """
    peak        = 0.0
    ruin_level  = r_thresh   # starts at -150 when peak=0

    for v in equity_curve:
        if v > peak:
            peak       = v
            ruin_level = peak + r_thresh   # trail up with new peak
        if v >= s_thresh:
            return 1.0
        if v <= ruin_level:
            return -1.0
    return 0.0   # neither threshold reached

@jit(nopython=True)
def build_equity_curve(trade_returns):
    """
    Build equity curve from trade returns.

    Args:
        trade_returns: Array of trade returns

    Returns:
        Cumulative equity curve
    """
    n = len(trade_returns)
    equity = np.zeros(n, dtype=np.float64)
    cumulative = 0.0

    for i in range(n):
        cumulative += trade_returns[i]
        equity[i] = cumulative

    return equity

def extract_trade_returns(strategy_returns):
    """
    Extract actual trade returns (non-zero values) from strategy returns.

    Args:
        strategy_returns: Array of strategy returns (includes zeros for non-trade periods)

    Returns:
        Array of actual trade returns
    """
    trade_returns = strategy_returns[strategy_returns != 0.0]
    return trade_returns

def calculate_rolling_sharpe(trade_returns, window=20):
    """
    Calculate rolling Sharpe ratio for a sequence of trade returns.

    For each rolling window of `window` trades, computes:
        sharpe = mean(window_returns) / std(window_returns) * sqrt(window)

    Args:
        trade_returns: Array of trade returns
        window: Rolling window size (number of trades)

    Returns:
        Array of rolling Sharpe values (length = max(0, n - window + 1))
    """
    n = len(trade_returns)
    if n < window:
        return np.array([], dtype=np.float64)

    rolling_sharpe = np.empty(n - window + 1, dtype=np.float64)
    for i in range(n - window + 1):
        w = trade_returns[i:i + window]
        mean_r = np.mean(w)
        std_r = np.std(w, ddof=1)
        rolling_sharpe[i] = (mean_r / std_r * np.sqrt(window)) if std_r > 0.0 else 0.0

    return rolling_sharpe

def run_monte_carlo(df, num_simulations=1000, sharpe_window=20, block_size=10):
    """
    Run Monte Carlo simulation using block bootstrap (sequence sampling).

    This method:
    1. Extracts actual trade returns from historical strategy run
    2. Samples consecutive blocks (sequences) of trades with replacement for
       each simulation — preserving local autocorrelation between trades
    3. Builds equity curves from the resampled sequences
    4. Calculates metrics (returns, drawdowns, EV, Sharpe, probability of ruin)

    Args:
        df:              DataFrame with historical data including strategy_returns
        num_simulations: Number of simulations to run
        sharpe_window:   Rolling window size (in trades) used for Sharpe calculations
        block_size:      Number of consecutive trades per bootstrap block/sequence

    Returns:
        Dictionary with:
        - equity_percentiles:        10th / 50th / 90th percentile equity curves
        - return_distribution:       Array of total returns per simulation
        - max_drawdown_distribution: Array of max drawdowns per simulation
        - expected_value_distribution: Array of per-trade EVs per simulation
        - sharpe_avg_distribution:   Array of mean rolling Sharpe per simulation
        - sharpe_std_distribution:   Array of std of rolling Sharpe per simulation
        - min_return_distribution:      Array of lowest equity reached per simulation
        - probability_of_ruin:          Fraction of sims that touched ruin_threshold
        - ruin_threshold:               The ruin threshold value used
        - probability_of_success:       Fraction of sims that hit success_threshold
                                        before hitting ruin_threshold
        - success_threshold:            The success threshold value used
        - time_points:               Trade indices for x-axis
        - num_original_trades:       Number of actual trades in historical data
        - block_size:                Block size used for sequence bootstrapping
        - sharpe_window:             Sharpe rolling window used
    """
    print(f"Running {num_simulations} Monte Carlo simulations using block bootstrap "
          f"(block_size={block_size})...")
    start_time = time.time()

    # Extract actual trade returns from strategy
    strategy_returns = df["strategy_returns"].fillna(0).values
    trade_returns = extract_trade_returns(strategy_returns)

    if len(trade_returns) == 0:
        raise ValueError("No trades found in historical data. Cannot run Monte Carlo simulation.")

    num_original_trades = len(trade_returns)
    print(f"  Found {num_original_trades} actual trades")

    # Calculate expected value from original trades
    original_ev = np.mean(trade_returns) if len(trade_returns) > 0 else 0.0

    # Number of blocks needed to cover num_original_trades
    num_blocks_needed = int(np.ceil(num_original_trades / block_size)) + 1

    equity_curves              = []
    return_distribution        = []
    max_drawdown_distribution  = []
    expected_value_distribution = []
    sharpe_avg_distribution    = []
    sharpe_std_distribution    = []
    min_return_distribution    = []
    outcome_counts = {1.0: 0, -1.0: 0, 0.0: 0}  # success / ruin-first / neither

    # Run simulations
    for sim_idx in range(num_simulations):
        np.random.seed(sim_idx)  # Reproducibility

        # Sample random block start positions (with replacement)
        block_starts = np.random.randint(
            0, max(1, num_original_trades - block_size + 1),
            size=num_blocks_needed
        ).astype(np.int32)

        # Block bootstrap sample
        sampled_trades = block_bootstrap_trades(
            trade_returns, num_original_trades, block_starts, block_size
        )

        # Build equity curve
        equity_curve = build_equity_curve(sampled_trades)

        # Core metrics
        total_return  = float(equity_curve[-1]) if len(equity_curve) > 0 else 0.0
        max_drawdown  = float(calculate_max_drawdown(equity_curve))
        expected_value = float(np.mean(sampled_trades)) if len(sampled_trades) > 0 else 0.0
        min_equity    = float(np.min(equity_curve)) if len(equity_curve) > 0 else 0.0

        # Rolling Sharpe statistics
        rolling_sharpe = calculate_rolling_sharpe(sampled_trades, window=sharpe_window)
        sharpe_avg = float(np.mean(rolling_sharpe)) if len(rolling_sharpe) > 0 else 0.0
        sharpe_std = float(np.std(rolling_sharpe, ddof=1)) if len(rolling_sharpe) > 1 else 0.0

        # Classify into exactly one outcome (mutually exclusive)
        outcome = classify_outcome(equity_curve, success_threshold, ruin_threshold)
        outcome_counts[outcome] += 1

        equity_curves.append(equity_curve)
        return_distribution.append(total_return)
        max_drawdown_distribution.append(max_drawdown)
        expected_value_distribution.append(expected_value)
        sharpe_avg_distribution.append(sharpe_avg)
        sharpe_std_distribution.append(sharpe_std)
        min_return_distribution.append(min_equity)

        if (sim_idx + 1) % 100 == 0:
            print(f"  Completed {sim_idx + 1}/{num_simulations} simulations")

    # Probability of Ruin (any touch, trailing drawdown) — for the histogram marker
    # A sim is "ruined at some point" if its max trailing drawdown >= abs(ruin_threshold).
    # calculate_max_drawdown already returns the peak-to-trough trailing drawdown.
    abs_ruin = abs(ruin_threshold)
    num_ruined_any = sum(1 for v in max_drawdown_distribution if v >= abs_ruin)
    probability_of_ruin = num_ruined_any / num_simulations if num_simulations > 0 else 0.0

    # Mutually-exclusive outcome probabilities (always sum to 1.0)
    n = num_simulations if num_simulations > 0 else 1
    probability_of_success      = outcome_counts[ 1.0] / n   # hit success first
    probability_of_ruin_first   = outcome_counts[-1.0] / n   # hit ruin first
    probability_of_neither      = outcome_counts[ 0.0] / n   # hit neither

    # Calculate percentile bands for equity curves
    max_length = max(len(curve) for curve in equity_curves) if equity_curves else 0

    if max_length > 0:
        padded_curves = []
        for curve in equity_curves:
            if len(curve) < max_length:
                padded = np.zeros(max_length, dtype=np.float64)
                padded[:len(curve)] = curve
                padded[len(curve):] = curve[-1] if len(curve) > 0 else 0.0
                padded_curves.append(padded)
            else:
                padded_curves.append(curve)

        equity_array = np.array(padded_curves)
        equity_percentiles = {
            "p10": np.percentile(equity_array, 10, axis=0).tolist(),
            "p50": np.percentile(equity_array, 50, axis=0).tolist(),
            "p90": np.percentile(equity_array, 90, axis=0).tolist(),
        }
        time_points = list(range(max_length))
    else:
        equity_percentiles = {"p10": [], "p50": [], "p90": []}
        time_points = []

    elapsed = time.time() - start_time
    print(f"Monte Carlo simulation completed in {elapsed:.2f}s")
    print(f"  Original trades:          {num_original_trades}")
    print(f"  Block size:               {block_size}")
    print(f"  Original EV:              {original_ev:.4f}")
    print(f"  Mean bootstrapped EV:     {np.mean(expected_value_distribution):.4f}")
    print(f"  Mean Sharpe (avg rolling):{np.mean(sharpe_avg_distribution):.4f}")
    print(f"  Mean Sharpe (std rolling):{np.mean(sharpe_std_distribution):.4f}")
    print(f"  Probability of Ruin (any):      {probability_of_ruin:.2%}")
    print(f"  Outcome — Success first:        {probability_of_success:.2%}")
    print(f"  Outcome — Ruin first:           {probability_of_ruin_first:.2%}")
    print(f"  Outcome — Neither:              {probability_of_neither:.2%}")

    return {
        "equity_percentiles":          equity_percentiles,
        "return_distribution":         return_distribution,
        "max_drawdown_distribution":   max_drawdown_distribution,
        "expected_value_distribution": expected_value_distribution,
        "sharpe_avg_distribution":     sharpe_avg_distribution,
        "sharpe_std_distribution":     sharpe_std_distribution,
        "min_return_distribution":     min_return_distribution,
        "probability_of_ruin":         probability_of_ruin,       # any touch (for histogram)
        "ruin_threshold":              ruin_threshold,
        "probability_of_success":      probability_of_success,    # hit success FIRST
        "probability_of_ruin_first":   probability_of_ruin_first, # hit ruin FIRST (exclusive)
        "probability_of_neither":      probability_of_neither,    # hit neither
        "success_threshold":           success_threshold,
        "time_points":                 time_points,
        "num_original_trades":         num_original_trades,
        "block_size":                  block_size,
        "sharpe_window":               sharpe_window,
    }
