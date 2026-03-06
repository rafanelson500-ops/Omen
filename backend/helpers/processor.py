import numpy as np
import time
from numba import jit

gbt_threshold = 0.6
gbt_max_threshold = 0.675

@jit(nopython=True)
def _process_strategy_numba(
    close, high, low, base_returns, gbt_target, mean, sigma,
    gbt_threshold, sl_coeff, tp_coeff
):
    """
    Numba-compiled core strategy processing logic.
    Returns position and strategy_returns arrays.
    """
    n = len(close)
    position = np.zeros(n, dtype=np.int32)
    strategy_returns = np.zeros(n, dtype=np.float64)
    
    current_position = 0
    entry_price = 0.0
    stop_loss = 0.0
    profit_target = 0.0
    prev_close = np.nan  # Use NaN as sentinel for "no previous close"
    
    for i in range(n):
        # Variables
        gbt_val = gbt_target[i]
        close_val = close[i]
        high_val = high[i]
        low_val = low[i]
        mean_val = mean[i]
        sigma_val = sigma[i]
        
        # Calculate strategy returns using position from previous bar
        prev_position = current_position
        bar_return = base_returns[i] * prev_position
        
        # Exit Criteria - simulate stop/limit orders using high/low of candle
        if prev_position != 0:
            exited = False
            exit_price = close_val  # Default to close if no exit
            
            if prev_position == 1:  # Long position
                # Calculate stop loss and take profit prices
                stop_loss_price = entry_price - stop_loss
                take_profit_price = entry_price + profit_target
                
                # Check if stop loss or take profit was hit during the candle
                if low_val <= stop_loss_price:
                    exit_price = stop_loss_price
                    exited = True
                elif high_val >= take_profit_price:
                    exit_price = take_profit_price
                    exited = True
                
                if close_val > mean_val:
                    exited = True
                    exit_price = close_val
                
                if exited:
                    # Calculate return from previous close to exit price
                    if not np.isnan(prev_close):
                        strategy_returns[i] = exit_price - prev_close
                    else:
                        # First bar after entry, use entry price
                        strategy_returns[i] = exit_price - entry_price
                    current_position = 0
                    entry_price = 0.0
                    stop_loss = 0.0
                    profit_target = 0.0
                    prev_close = np.nan
                else:
                    # No exit, use full bar return
                    strategy_returns[i] = bar_return
                    prev_close = close_val
                    
            elif prev_position == -1:  # Short position
                # Calculate stop loss and take profit prices
                stop_loss_price = entry_price + stop_loss
                take_profit_price = entry_price - profit_target
                
                # Check if stop loss or take profit was hit during the candle
                if high_val >= stop_loss_price:
                    exit_price = stop_loss_price
                    exited = True
                elif low_val <= take_profit_price:
                    exit_price = take_profit_price
                    exited = True
                
                if close_val > mean_val:
                    exited = True
                    exit_price = close_val
                
                if exited:
                    # Calculate return from previous close to exit price (inverted for short)
                    if not np.isnan(prev_close):
                        strategy_returns[i] = prev_close - exit_price
                    else:
                        # First bar after entry, use entry price
                        strategy_returns[i] = entry_price - exit_price
                    current_position = 0
                    entry_price = 0.0
                    stop_loss = 0.0
                    profit_target = 0.0
                    prev_close = np.nan
                else:
                    # No exit, use full bar return
                    strategy_returns[i] = bar_return
                    prev_close = close_val
        else:
            # No position, no return
            strategy_returns[i] = 0.0
            prev_close = close_val
        
        # Entry Criteria - only enter if flat
        if current_position == 0:
            if gbt_val > gbt_threshold and gbt_val < gbt_max_threshold:
                if close_val > mean_val + 0.5 * sigma_val:
                    # Short position
                    current_position = -1
                    entry_price = close_val
                    stop_loss = round(sl_coeff * sigma_val * 4) / 4  # Stop loss: rounded to nearest 0.25
                    profit_target = round(tp_coeff * sigma_val * 4) / 4  # Profit target: rounded to nearest 0.25
                    prev_close = close_val
                elif close_val < mean_val - 0.5 * sigma_val:
                    # Long position
                    current_position = 1
                    entry_price = close_val
                    stop_loss = round(sl_coeff * sigma_val * 4) / 4  # Stop loss: rounded to nearest 0.25
                    profit_target = round(tp_coeff * sigma_val * 4) / 4  # Profit target: rounded to nearest 0.25
                    prev_close = close_val
        
        # Store current position
        position[i] = current_position
    
    return position, strategy_returns

def process_data(df):
    time_start = time.time()
    df["base_returns"] = df["close"] - df["close"].shift(1)
    df["base_returns"] = np.where(df["new_session"] == 1, 0, df["base_returns"])

    # Extract arrays for Numba processing
    close = df["close"].values
    high = df["high"].values
    low = df["low"].values
    base_returns = df["base_returns"].values
    gbt_target = df["gbt_target"].fillna(0).values  # Fill NaN with 0 for Numba
    mean = df["composite_mean"].values
    sigma = df["har_sigma"].values
    
    sl_coeff = 1.5
    tp_coeff = 4
    
    # Process with Numba
    position, strategy_returns = _process_strategy_numba(
        close, high, low, base_returns, gbt_target, mean, sigma,
        gbt_threshold, sl_coeff, tp_coeff
    )
    
    # Write results back to DataFrame
    df["position"] = position
    df["strategy_returns"] = strategy_returns
    
    df["base_cumulative"] = df["base_returns"].cumsum()
    df["strategy_cumulative"] = df["strategy_returns"].cumsum()
    print(f"Processing time: {time.time() - time_start:.3f}s")
    return df