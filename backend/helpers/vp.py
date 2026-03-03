import numpy as np
import pandas as pd
from numba import jit

@jit(nopython=True, cache=True)
def _compute_volume_profile_numba(lows, highs, volumes, price_step):
    """
    Numba-accelerated volume profile computation for a single window.
    Uses bin indices for O(1) lookups instead of price matching.
    Returns sorted prices and volumes arrays.
    """
    if len(lows) == 0:
        return np.empty(0, dtype=np.float64), np.empty(0, dtype=np.float64)
    
    # Find price range and calculate bin indices
    min_price = np.min(lows)
    max_price = np.max(highs)
    
    # Calculate bin range
    min_bin_idx = int(np.floor(min_price / price_step))
    max_bin_idx = int(np.ceil(max_price / price_step)) + 1
    
    # Pre-allocate volume array using bin indices (much faster than price matching)
    num_bins = max_bin_idx - min_bin_idx + 1
    volume_bins = np.zeros(num_bins, dtype=np.float64)
    
    # Process each candle
    for j in range(len(lows)):
        if volumes[j] <= 0:
            continue
            
        low = lows[j]
        high = highs[j]
        vol = volumes[j]
        
        # Calculate price range
        price_range = high - low
        if price_range <= 0:
            continue
        
        # Calculate bin indices
        low_bin_idx = int(np.floor(low / price_step))
        high_bin_idx = int(np.ceil(high / price_step))
        
        # Ensure indices are within range
        low_bin_idx = max(low_bin_idx, min_bin_idx)
        high_bin_idx = min(high_bin_idx, max_bin_idx)
        
        if high_bin_idx < low_bin_idx:
            continue
        
        # Calculate number of bins and volume per bin
        num_price_bins = high_bin_idx - low_bin_idx + 1
        vol_per_bin = vol / num_price_bins
        
        # Accumulate volume in bins (O(1) access)
        for bin_idx in range(low_bin_idx, high_bin_idx + 1):
            array_idx = bin_idx - min_bin_idx
            volume_bins[array_idx] += vol_per_bin
    
    # Convert bin indices back to prices and filter out zero-volume bins
    valid_mask = volume_bins > 0
    if not np.any(valid_mask):
        return np.empty(0, dtype=np.float64), np.empty(0, dtype=np.float64)
    
    # Build arrays of prices and volumes for valid bins
    valid_indices = np.where(valid_mask)[0]
    num_valid = len(valid_indices)
    prices = np.zeros(num_valid, dtype=np.float64)
    for k in range(num_valid):
        prices[k] = (min_bin_idx + valid_indices[k]) * price_step
    vols = volume_bins[valid_mask]
    
    # Sort by volume descending
    sort_idx = np.argsort(vols)[::-1]
    return prices[sort_idx], vols[sort_idx]


@jit(nopython=True, cache=True)
def _calculate_value_area(prices_sorted, vols_sorted, value_area_pct):
    """Calculate VAL and VAH from sorted volume profile."""
    if len(prices_sorted) == 0:
        return np.nan, np.nan
    
    total_volume = np.sum(vols_sorted)
    if total_volume <= 0:
        return np.nan, np.nan
    
    target_volume = total_volume * value_area_pct
    cumulative = np.cumsum(vols_sorted)
    
    # Find first index where cumulative >= target_volume
    idx = 0
    for i in range(len(cumulative)):
        if cumulative[i] >= target_volume:
            idx = i
            break
    
    selected_prices = prices_sorted[:idx + 1]
    if len(selected_prices) == 0:
        return np.nan, np.nan
    
    val = np.min(selected_prices)
    vah = np.max(selected_prices)
    return val, vah


def add_value_area_levels(df, lookback=100, price_step=0.25, value_area_pct=0.7):
    """
    Adds VAL, VAH, and POC columns to a candle dataframe using rolling volume profile.
    Highly optimized version using numba JIT compilation.

    Parameters:
        df (pd.DataFrame): Must contain columns ["Low","High","Volume"]
        lookback (int): Number of candles in rolling window
        price_step (float): Price bin size
        value_area_pct (float): % of volume to include in value area (default 70%)

    Returns:
        pd.DataFrame with added columns ["VAL", "VAH", "POC"]
    """
    
    df = df.copy()
    df["val"] = np.nan
    df["vah"] = np.nan
    df["poc"] = np.nan
    
    # Convert to numpy arrays for faster access
    lows = df["low"].values.astype(np.float64)
    highs = df["high"].values.astype(np.float64)
    volumes = df["volume"].values.astype(np.float64)
    
    # Pre-allocate result arrays
    val_results = np.full(len(df), np.nan, dtype=np.float64)
    vah_results = np.full(len(df), np.nan, dtype=np.float64)
    poc_results = np.full(len(df), np.nan, dtype=np.float64)
    
    # Calculate volume profile for every candle to avoid look-ahead bias
    # This ensures each candle's VAL/VAH/POC is based only on the lookback window ending at that candle
    for i in range(lookback, len(df)):
        start_idx = i - lookback
        window_lows = lows[start_idx:i]
        window_highs = highs[start_idx:i]
        window_volumes = volumes[start_idx:i]
        
        # Filter out zero-volume candles
        valid_mask = window_volumes > 0
        if not np.any(valid_mask):
            continue
            
        window_lows = window_lows[valid_mask]
        window_highs = window_highs[valid_mask]
        window_volumes = window_volumes[valid_mask]
        
        # Compute volume profile using numba
        prices_sorted, vols_sorted = _compute_volume_profile_numba(
            window_lows, window_highs, window_volumes, price_step
        )
        
        if len(prices_sorted) == 0:
            continue
        
        # Calculate value area
        val, vah = _calculate_value_area(prices_sorted, vols_sorted, value_area_pct)
        val_results[i] = val
        vah_results[i] = vah
        
        # Calculate POC (Point of Control) - price with highest volume
        # prices_sorted is already sorted by volume descending, so first element is POC
        poc_results[i] = prices_sorted[0]
    
    # Assign results back to dataframe (much faster than iloc)
    df["val"] = val_results
    df["vah"] = vah_results
    df["poc"] = poc_results
    
    return df