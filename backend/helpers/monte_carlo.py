import numpy as np
import pandas as pd
from numba import jit
import time

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
def bootstrap_sample_trades(trade_returns, num_trades, random_indices):
    """
    Bootstrap sample trades with replacement.
    
    Args:
        trade_returns: Array of actual trade returns
        num_trades: Number of trades to sample (typically same as original)
        random_indices: Pre-generated random indices for sampling
    
    Returns:
        Array of sampled trade returns
    """
    n_trades = len(trade_returns)
    if n_trades == 0:
        return np.zeros(num_trades, dtype=np.float64)
    
    sampled_trades = np.zeros(num_trades, dtype=np.float64)
    for i in range(num_trades):
        # Use modulo to cycle through random_indices if needed
        idx = random_indices[i % len(random_indices)] % n_trades
        sampled_trades[i] = trade_returns[idx]
    
    return sampled_trades

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
    # Filter out zero returns (non-trade periods)
    trade_returns = strategy_returns[strategy_returns != 0.0]
    return trade_returns

def run_monte_carlo(df, num_simulations=1000):
    """
    Run Monte Carlo simulation using bootstrapping (random sampling with replacement).
    
    This method:
    1. Extracts actual trade returns from historical strategy run
    2. Randomly samples trades with replacement for each simulation
    3. Builds equity curves from sampled trades
    4. Calculates metrics (returns, drawdowns, expected value)
    
    Args:
        df: DataFrame with historical data including strategy_returns
        num_simulations: Number of simulations to run
    
    Returns:
        Dictionary with:
        - equity_percentiles: Dictionary with 10th, 50th, 90th percentile curves
        - return_distribution: Array of total returns
        - max_drawdown_distribution: Array of max drawdowns
        - expected_value_distribution: Array of expected values
        - time_points: Time points for x-axis (trade indices)
    """
    print(f"Running {num_simulations} Monte Carlo simulations using bootstrapping...")
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
    
    equity_curves = []
    return_distribution = []
    max_drawdown_distribution = []
    expected_value_distribution = []
    
    # Run simulations
    for sim_idx in range(num_simulations):
        # Generate random indices for bootstrap sampling
        np.random.seed(sim_idx)  # Use simulation index as seed for reproducibility
        # Sample same number of trades as original (with replacement)
        random_indices = np.random.randint(0, num_original_trades, size=num_original_trades).astype(np.int32)
        
        # Bootstrap sample trades
        sampled_trades = bootstrap_sample_trades(trade_returns, num_original_trades, random_indices)
        
        # Build equity curve
        equity_curve = build_equity_curve(sampled_trades)
        
        # Calculate metrics
        total_return = equity_curve[-1] if len(equity_curve) > 0 else 0.0
        max_drawdown = calculate_max_drawdown(equity_curve)
        expected_value = np.mean(sampled_trades) if len(sampled_trades) > 0 else 0.0
        
        equity_curves.append(equity_curve)
        return_distribution.append(total_return)
        max_drawdown_distribution.append(max_drawdown)
        expected_value_distribution.append(expected_value)
        
        if (sim_idx + 1) % 100 == 0:
            print(f"  Completed {sim_idx + 1}/{num_simulations} simulations")
    
    # Calculate percentile bands for equity curves
    # Pad all curves to same length (use max length)
    max_length = max(len(curve) for curve in equity_curves) if equity_curves else 0
    
    if max_length > 0:
        # Pad shorter curves with their last value
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
        
        # Create time points (trade indices)
        time_points = list(range(max_length))
    else:
        equity_percentiles = {"p10": [], "p50": [], "p90": []}
        time_points = []
    
    elapsed = time.time() - start_time
    print(f"Monte Carlo simulation completed in {elapsed:.2f}s")
    print(f"  Original trades: {num_original_trades}")
    print(f"  Original EV: {original_ev:.4f}")
    print(f"  Mean bootstrapped EV: {np.mean(expected_value_distribution):.4f}")
    
    return {
        "equity_percentiles": equity_percentiles,
        "return_distribution": return_distribution,
        "max_drawdown_distribution": max_drawdown_distribution,
        "expected_value_distribution": expected_value_distribution,
        "time_points": time_points,
        "num_original_trades": num_original_trades,
    }
