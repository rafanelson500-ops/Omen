"""
Data loader for SPY ticker historical data.
Fetches OHLCV data from yfinance and returns a clean DataFrame.
"""

import yfinance as yf
import pandas as pd
from typing import Optional


def load_spy_data(period: str = "5y", start: Optional[str] = None, end: Optional[str] = None, interval: str = "1d") -> pd.DataFrame:
    """
    Load historical data for SPY ticker.
    
    Args:
        period: Valid periods: 1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max
        start: Start date string (YYYY-MM-DD). If provided, period is ignored.
        end: End date string (YYYY-MM-DD). If provided, period is ignored.
        interval: Valid intervals: 1m, 2m, 5m, 15m, 30m, 60m, 90m, 1h, 1d, 5d, 1wk, 1mo, 3mo
    
    Returns:
        DataFrame with columns: Open, High, Low, Close, Volume
    """
    ticker = yf.Ticker("SPY")
    
    if start and end:
        df = ticker.history(start=start, end=end, interval=interval)
    elif start:
        df = ticker.history(start=start, interval=interval)
    else:
        df = ticker.history(period=period, interval=interval)
    
    # Ensure column names are capitalized
    df.columns = [col.capitalize() for col in df.columns]
    
    # Select only the required columns
    required_cols = ['Open', 'High', 'Low', 'Close', 'Volume']
    df = df[required_cols].copy()
    
    # Remove any rows with NaN values
    df = df.dropna()
    
    # Reset index to have Date as a column (optional, but useful)
    df.reset_index(inplace=True)
    if 'Date' in df.columns:
        df.set_index('Date', inplace=True)
    
    return df
