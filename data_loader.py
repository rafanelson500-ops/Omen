import numpy as np
import pandas as pd
import yfinance as yf
from typing import List, Tuple
import warnings

# Suppress yfinance deprecation warning (it's in their library, not our code)
warnings.filterwarnings('ignore', message='.*Timestamp.utcnow.*')
warnings.filterwarnings('ignore', message='.*Pandas4Warning.*')


def engineer_features(ohlcv: np.ndarray) -> np.ndarray:
    """
    Convert OHLCV to feature array.
    
    Args:
        ohlcv: Shape (time_steps, 5) - [open, high, low, close, volume]
    
    Returns:
        features: Shape (time_steps, 18)
    """
    time_steps = ohlcv.shape[0]
    features_list = []
    
    open_p = ohlcv[:, 0]
    high_p = ohlcv[:, 1]
    low_p = ohlcv[:, 2]
    close_p = ohlcv[:, 3]
    volume = ohlcv[:, 4]
    
    # Normalize prices relative to close price (more stable than raw prices)
    # This makes features scale-independent
    open_norm = open_p / (close_p + 1e-8)
    high_norm = high_p / (close_p + 1e-8)
    low_norm = low_p / (close_p + 1e-8)
    close_norm = np.ones_like(close_p)  # Always 1.0 (reference)
    
    # Normalize volume - use log scale and relative to recent average
    volume_ma_recent = np.convolve(volume, np.ones(20)/20, mode='same')
    volume_norm = np.log1p(volume / (volume_ma_recent + 1e-8))  # Log of ratio
    
    # Add normalized features
    features_list.extend([open_norm, high_norm, low_norm, close_norm, volume_norm])
    
    # Returns
    returns = np.diff(close_p, prepend=close_p[0]) / (close_p + 1e-8)
    features_list.append(returns)
    
    # High-Low spread
    hl_spread = (high_p - low_p) / (close_p + 1e-8)
    features_list.append(hl_spread)
    
    # Body size
    body = (close_p - open_p) / (close_p + 1e-8)
    features_list.append(body)
    
    # Wicks
    upper_wick = (high_p - np.maximum(open_p, close_p)) / (close_p + 1e-8)
    lower_wick = (np.minimum(open_p, close_p) - low_p) / (close_p + 1e-8)
    features_list.extend([upper_wick, lower_wick])
    
    # Volume features
    volume_ma = np.convolve(volume, np.ones(5)/5, mode='same')
    volume_ratio = volume / (volume_ma + 1e-8)
    features_list.append(volume_ratio)
    
    # Moving averages
    ma5 = np.convolve(close_p, np.ones(5)/5, mode='same')
    ma20 = np.convolve(close_p, np.ones(20)/20, mode='same')
    features_list.extend([
        close_p / (ma5 + 1e-8),
        close_p / (ma20 + 1e-8),
        ma5 / (ma20 + 1e-8)
    ])
    
    # RSI-like
    price_changes = np.diff(close_p, prepend=close_p[0])
    gains = np.where(price_changes > 0, price_changes, 0)
    losses = np.where(price_changes < 0, -price_changes, 0)
    avg_gain = np.convolve(gains, np.ones(14)/14, mode='same')
    avg_loss = np.convolve(losses, np.ones(14)/14, mode='same')
    rs = avg_gain / (avg_loss + 1e-8)
    rsi = 100 - (100 / (1 + rs))
    features_list.append(rsi / 100.0)
    
    # Volatility
    returns_std = np.array([
        np.std(returns[max(0, i-10):i+1]) if i > 0 else 0
        for i in range(time_steps)
    ])
    features_list.append(returns_std)
    
    # Stack into array
    features = np.column_stack(features_list)
    
    return features.astype(np.float32)


def get_data(
    symbols: List[str], 
    timeframes: List[str], 
    time_steps: int = 100
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Downloads stock data and returns formatted arrays for training.
    
    Args:
        symbols: List of stock symbols, e.g., ["SPY", "QQQ"]
        timeframes: List of timeframes, e.g., ["30m", "1h", "1d"]
        time_steps: Number of historical candles to use for each sample
    
    Returns:
        X: Input features shape (samples, symbols, timeframes, time_steps, features)
        y: Target percent changes shape (samples, symbols, timeframes) - percent change from current to next candle
           Formula: (next_close - current_close) / current_close
    """
    
    # Step 1: Download all data
    all_data = {}
    for symbol in symbols:
        all_data[symbol] = {}
        ticker = yf.Ticker(symbol)
        
        for tf in timeframes:
            try:
                df = ticker.history(interval=tf, period="max")
                if df.empty:
                    print(f"Warning: No data for {symbol} {tf}")
                    continue
                
                # Keep only OHLCV columns
                df = df[['Open', 'High', 'Low', 'Close', 'Volume']]
                df.dropna(inplace=True)
                
                if len(df) < time_steps + 1:
                    print(f"Warning: {symbol} {tf} has only {len(df)} candles, need {time_steps + 1}")
                    continue
                
                all_data[symbol][tf] = df
            except Exception as e:
                print(f"Error downloading {symbol} {tf}: {e}")
                continue
    
    # Step 2: Find minimum length across all symbols/timeframes
    if not all_data:
        raise ValueError("No data downloaded! Check symbols and timeframes.")
    
    lengths = [
        len(df) 
        for symbol_data in all_data.values() 
        for df in symbol_data.values()
    ]
    
    if not lengths:
        raise ValueError("No valid data found!")
    
    min_length = min(lengths)
    
    # Step 3: Calculate number of samples we can create
    num_samples = min_length - time_steps - 1  # -1 for target
    
    if num_samples <= 0:
        raise ValueError(f"Not enough data! Need at least {time_steps + 1} candles, got {min_length}")
    
    # Step 4: Engineer features ONCE for each symbol/timeframe
    # This is much faster than recalculating for each sliding window
    all_features = {}  # {symbol: {timeframe: feature_array}}
    all_close_prices = {}  # {symbol: {timeframe: close_price_array}} - needed for percent change
    
    for symbol in symbols:
        all_features[symbol] = {}
        all_close_prices[symbol] = {}
        
        for tf in timeframes:
            if symbol not in all_data or tf not in all_data[symbol]:
                continue
            
            df = all_data[symbol][tf]
            
            # Extract OHLCV for entire dataset
            ohlcv = df[['Open', 'High', 'Low', 'Close', 'Volume']].values
            
            # Engineer features ONCE for all data
            features = engineer_features(ohlcv)  # Shape: (total_candles, 18)
            all_features[symbol][tf] = features
            
            # Store close prices for calculating percent change
            close_prices = df['Close'].values  # Shape: (total_candles,)
            all_close_prices[symbol][tf] = close_prices
    
    # Step 5: Create sliding windows from already-featurized data
    num_features = 16  # 5 base + 13 engineered
    X = np.zeros((num_samples, len(symbols), len(timeframes), time_steps, num_features), 
                 dtype=np.float32)
    y = np.zeros((num_samples, len(symbols), len(timeframes)), dtype=np.float32)
    
    for sample_idx in range(num_samples):
        for sym_idx, symbol in enumerate(symbols):
            for tf_idx, timeframe in enumerate(timeframes):
                # Check if data exists for this symbol/timeframe
                if symbol not in all_features or timeframe not in all_features[symbol]:
                    continue
                
                features = all_features[symbol][timeframe]
                close_prices = all_close_prices[symbol][timeframe]
                
                # Just slice the already-featurized data - FAST!
                window = features[sample_idx:sample_idx + time_steps]  # Shape: (time_steps, 18)
                X[sample_idx, sym_idx, tf_idx, :, :] = window
                
                # Calculate percent change target
                # Window ends at index sample_idx + time_steps - 1
                # Current close is at index sample_idx + time_steps - 1
                # Next close is at index sample_idx + time_steps
                current_idx = sample_idx + time_steps - 1
                next_idx = sample_idx + time_steps
                
                if next_idx < len(close_prices):
                    current_close = close_prices[current_idx]
                    next_close = close_prices[next_idx]
                    
                    # Calculate percent change: (next - current) / current
                    percent_change = (next_close - current_close) / (current_close + 1e-8)
                    y[sample_idx, sym_idx, tf_idx] = percent_change
    
    return X, y