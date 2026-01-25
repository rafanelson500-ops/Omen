"""
Feature calculation for HMM model.
Computes returns, realized volatility, and autocorrelation from SPY data.
"""

import pandas as pd
import numpy as np
from typing import Tuple


def calculate_returns(df: pd.DataFrame) -> pd.Series:
    """
    Compute log returns from Close prices.
    
    Args:
        df: DataFrame with Close column
    
    Returns:
        Series of log returns
    """
    returns = np.log(df['Close'] / df['Close'].shift(1))
    return returns


def calculate_realized_vol(returns: pd.Series, window: int = 20) -> pd.Series:
    """
    Calculate rolling realized volatility (standard deviation of returns).
    
    Args:
        returns: Series of returns
        window: Rolling window size in days
    
    Returns:
        Series of realized volatility
    """
    realized_vol = returns.rolling(window=window).std()
    return realized_vol


def calculate_autocorrelation(returns: pd.Series, window: int = 20, lag: int = 1) -> pd.Series:
    """
    Calculate rolling autocorrelation of returns at specified lag.
    
    Args:
        returns: Series of returns
        window: Rolling window size in days
        lag: Lag for autocorrelation calculation (default: 1)
    
    Returns:
        Series of autocorrelation values
    """
    autocorr = pd.Series(index=returns.index, dtype=float)
    
    for i in range(window, len(returns)):
        window_returns = returns.iloc[i-window:i]
        if len(window_returns) > lag and window_returns.std() > 0:
            autocorr.iloc[i] = window_returns.autocorr(lag=lag)
        else:
            autocorr.iloc[i] = np.nan
    
    return autocorr


def prepare_features(df: pd.DataFrame, vol_window: int = 20, autocorr_window: int = 20) -> Tuple[pd.DataFrame, np.ndarray]:
    """
    Prepare all features for HMM model: returns, realized_vol, autocorrelation.
    Normalizes features and returns both raw DataFrame and normalized array.
    
    Args:
        df: DataFrame with Close column
        vol_window: Window size for realized volatility calculation
        autocorr_window: Window size for autocorrelation calculation
    
    Returns:
        Tuple of (features_df, normalized_features_array)
        features_df contains: returns, realized_vol, autocorrelation
        normalized_features_array is ready for HMM input
    """
    # Calculate returns
    returns = calculate_returns(df)
    
    # Calculate realized volatility
    realized_vol = calculate_realized_vol(returns, window=vol_window)
    
    # Calculate autocorrelation
    autocorr = calculate_autocorrelation(returns, window=autocorr_window, lag=1)
    
    # Create features DataFrame
    features_df = pd.DataFrame({
        'returns': returns,
        'realized_vol': realized_vol,
        'autocorrelation': autocorr
    }, index=df.index)
    
    # Drop rows with NaN values (from rolling calculations)
    features_df = features_df.dropna()
    
    # Normalize features (standardization)
    features_normalized = features_df.copy()
    features_normalized['returns'] = (features_df['returns'] - features_df['returns'].mean()) / features_df['returns'].std()
    features_normalized['realized_vol'] = (features_df['realized_vol'] - features_df['realized_vol'].mean()) / features_df['realized_vol'].std()
    features_normalized['autocorrelation'] = (features_df['autocorrelation'] - features_df['autocorrelation'].mean()) / features_df['autocorrelation'].std()
    
    # Replace any remaining NaN or inf values with 0
    features_normalized = features_normalized.replace([np.inf, -np.inf], np.nan).fillna(0)
    
    # Convert to numpy array for HMM
    features_array = features_normalized[['returns', 'realized_vol', 'autocorrelation']].values
    
    return features_df, features_array
