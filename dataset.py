"""
Dataset creation and feature engineering.
Computes derived features and builds sequences for model training.
"""

import pandas as pd
import numpy as np
from typing import Tuple


def compute_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute derived features from OHLCV data.
    
    Features computed:
    - PctChange: Percentage change from Open to Close
    - IsGreen: 1 if Close >= Open, 0 otherwise
    - UpperWickLength: High - max(Open, Close)
    - LowerWickLength: min(Open, Close) - Low
    
    Args:
        df: DataFrame with columns Open, High, Low, Close, Volume
    
    Returns:
        DataFrame with all original columns plus derived features
    """
    df = df.copy()
    
    # PctChange: (Close - Open) / Open * 100
    df['PctChange'] = ((df['Close'] - df['Open']) / df['Open']) * 100
    
    # IsGreen: 1 if Close >= Open, else 0
    df['IsGreen'] = (df['Close'] >= df['Open']).astype(int)
    
    # UpperWickLength: High - max(Open, Close)
    df['UpperWickLength'] = df['High'] - df[['Open', 'Close']].max(axis=1)
    
    # LowerWickLength: min(Open, Close) - Low
    df['LowerWickLength'] = df[['Open', 'Close']].min(axis=1) - df['Low']
    
    return df


def create_sequences(df: pd.DataFrame, sequence_length: int = 10) -> Tuple[np.ndarray, np.ndarray]:
    """
    Create sequences of candles and labels for training.
    
    Each sequence contains `sequence_length` consecutive candles.
    The label is the IsGreen value of the next candle after the sequence.
    
    Args:
        df: DataFrame with all features (Open, High, Low, Close, Volume, PctChange, IsGreen, UpperWickLength, LowerWickLength)
        sequence_length: Number of candles in each sequence
    
    Returns:
        X: Array of shape (n_samples, sequence_length, n_features)
        y: Array of shape (n_samples,) with IsGreen labels
    """
    # Feature columns to use (excluding IsGreen from input features)
    feature_cols = ['Open', 'High', 'Low', 'Close', 'Volume', 'PctChange', 
                    'UpperWickLength', 'LowerWickLength']
    
    # Convert to numpy arrays
    features = df[feature_cols].values
    labels = df['IsGreen'].values
    
    X = []
    y = []
    
    # Create sequences
    for i in range(len(df) - sequence_length):
        # Sequence of candles
        sequence = features[i:i + sequence_length]
        # Label is the IsGreen value of the next candle
        label = labels[i + sequence_length]
        
        X.append(sequence)
        y.append(label)
    
    return np.array(X), np.array(y)


def flatten_sequences(X: np.ndarray) -> np.ndarray:
    """
    Flatten sequences for gradient boosted trees.
    
    Gradient boosted trees expect 2D input (n_samples, n_features),
    so we flatten the sequence dimension.
    
    Args:
        X: Array of shape (n_samples, sequence_length, n_features)
    
    Returns:
        Flattened array of shape (n_samples, sequence_length * n_features)
    """
    n_samples, sequence_length, n_features = X.shape
    return X.reshape(n_samples, sequence_length * n_features)
