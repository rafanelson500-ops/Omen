"""
Prediction module for loading saved models and making predictions.
"""

import joblib
import numpy as np
import pandas as pd
from dataset import compute_features, create_sequences, flatten_sequences
from typing import Tuple


def load_model(model_path: str = "boil_model.pkl"):
    """
    Load a saved model from disk.
    
    Args:
        model_path: Path to the saved model file
    
    Returns:
        Loaded model
    """
    return joblib.load(model_path)


def predict_next_candle(model, df: pd.DataFrame, sequence_length: int = 10, 
                       start_idx: int = None) -> Tuple[int, float]:
    """
    Predict the IsGreen value of the next candle given a sequence.
    
    Args:
        model: Trained GradientBoostingClassifier model
        df: DataFrame with all features (must have been processed with compute_features)
        sequence_length: Number of candles in the sequence
        start_idx: Starting index for the sequence. If None, uses the last sequence_length candles.
    
    Returns:
        Tuple of (predicted_class, predicted_probability)
    """
    # Compute features if not already done
    if 'PctChange' not in df.columns:
        df = compute_features(df)
    
    # Determine sequence indices
    if start_idx is None:
        # Use the last sequence_length candles
        start_idx = len(df) - sequence_length
    
    if start_idx + sequence_length > len(df):
        raise ValueError(f"Not enough data: need {sequence_length} candles starting at index {start_idx}")
    
    # Extract sequence
    feature_cols = ['Open', 'High', 'Low', 'Close', 'Volume', 'PctChange', 
                    'UpperWickLength', 'LowerWickLength', 'IsLastCandle']
    sequence = df[feature_cols].iloc[start_idx:start_idx + sequence_length].values
    
    # Reshape for model (add batch dimension, then flatten)
    sequence_flat = sequence.reshape(1, -1)
    
    # Predict
    predicted_class = model.predict(sequence_flat)[0]
    predicted_proba = model.predict_proba(sequence_flat)[0]
    
    # Probability of IsGreen=1
    prob_green = predicted_proba[1] if len(predicted_proba) > 1 else predicted_proba[0]
    
    return int(predicted_class), float(prob_green)
