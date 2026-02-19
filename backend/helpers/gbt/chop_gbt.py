import numpy as np
import pandas as pd
from typing import Tuple
from sklearn.ensemble import GradientBoostingRegressor
import os
from .gbt_helper import create_sequences, SEQUENCE_LENGTH, _resolve_path
import joblib

features = [
    'open', 'high', 'low', 'close', 'volume', 'dist_to_val', 'dist_to_vah', 'dist_to_vwap', 'upper_wick', 'lower_wick', 'wick_ratio', 'dir', 'persistence_5'
]

def train_chop_gbt(data: pd.DataFrame) -> GradientBoostingRegressor:
    """
    Train GBT model on sequences.
    
    Args:
        data: DataFrame with all features including 'ForwardReturn'
    
    Returns:
        Trained GradientBoostingRegressor model
    
    Raises:
        ValueError: If no valid training data after removing NaNs
    """
    save_path = "trained_models/chop_gbt_model.pkl"
    # Create sequences from data
    X_sequences, y_targets = create_sequences(data)
    
    # Remove NaN targets (from forward-looking calculation)
    valid_mask = ~np.isnan(y_targets)
    X_sequences = X_sequences[valid_mask]
    y_targets = y_targets[valid_mask]
    
    # Also remove any rows with NaN in features
    feature_nan_mask = ~np.isnan(X_sequences).any(axis=1)
    X_sequences = X_sequences[feature_nan_mask]
    y_targets = y_targets[feature_nan_mask]
    
    # Check if we have enough data to train
    if len(X_sequences) == 0:
        raise ValueError("No valid training data after removing NaN values. Check input data quality.")
    
    if len(X_sequences) < 10:
        raise ValueError(f"Insufficient training data: only {len(X_sequences)} samples available. Need at least 10.")
    
    try:
        model = GradientBoostingRegressor(
            n_estimators=100,
            learning_rate=0.1,
            max_depth=5,
            random_state=40,
            verbose=1
        )
        model.fit(X_sequences, y_targets)
        save_model(model, save_path)
        return model
    except ValueError as e:
        if "NaN" in str(e) or "missing values" in str(e).lower():
            raise ValueError(f"Training failed due to NaN values in features. "
                           f"Valid samples: {len(X_sequences)}, "
                           f"Features with NaN: {np.isnan(X_sequences).sum(axis=0)}") from e
        raise

def predict_chop_target(model, data: pd.DataFrame) -> pd.DataFrame:
    """
    Predict target values using the trained model and add chop_signal to the data.
    
    Args:
        model: Trained GradientBoostingRegressor model
        data: DataFrame with all required features (must match training columns)
    
    Returns:
        DataFrame with added 'chop_signal' column (binary_prediction * confidence, where
        binary_prediction is 1 or -1 and confidence is 0-1)
    """
    # Match create_sequences behavior: it uses data.values which includes ALL columns
    # But we need to handle NaN in target columns (forward_return, target) for recent candles
    # Fill NaN in target columns with 0 so model can make predictions
    target_cols = ['forward_return', 'target', 'chop_signal']
    feature_cols = [col for col in data.columns if col not in target_cols]
    
    # Create a copy of data and fill NaN in target columns with 0 for sequence creation
    data_for_sequences = data.copy()
    for col in target_cols:
        if col in data_for_sequences.columns:
            data_for_sequences[col] = data_for_sequences[col].fillna(0)
    
    # Get all data (including target cols) to match training format
    all_data = data_for_sequences.values
    # Get feature-only data for NaN checking
    feature_data = data[feature_cols].values
    
    # Create sequences for prediction (matching create_sequences format)
    X_sequences = []
    valid_indices = []
    
    # Create sliding windows starting from SEQUENCE_LENGTH
    for i in range(SEQUENCE_LENGTH, len(data)):
        # Check if sequence has any NaN values in FEATURE columns only
        # (ignore NaN in target columns like forward_return/target for recent candles)
        feature_sequence = feature_data[i - SEQUENCE_LENGTH:i]
        if np.isnan(feature_sequence).any():
            continue
        # Get sequence of previous candles (all columns to match training, with NaN filled)
        sequence = all_data[i - SEQUENCE_LENGTH:i]
        # Flatten the sequence into a single feature vector (matching create_sequences)
        flattened_sequence = sequence.flatten()
        X_sequences.append(flattened_sequence)
        valid_indices.append(i)
    
    # Initialize chop_signal column with NaN
    data['chop_signal'] = np.nan
    
    if len(X_sequences) == 0:
        return data
    
    X_sequences = np.array(X_sequences)
    
    # Verify feature count matches model expectations
    expected_features = model.n_features_in_
    actual_features = X_sequences.shape[1]
    if actual_features != expected_features:
        raise ValueError(
            f"Feature count mismatch: model expects {expected_features} features, "
            f"but got {actual_features}. This usually means the data columns don't match "
            f"what was used during training. Current columns: {list(data.columns)}"
        )
    
    # Make predictions (continuous regression values)
    predictions = model.predict(X_sequences)
    
    # Convert to binary prediction: 1 for positive, -1 for negative
    binary_prediction = np.where(predictions > 0, 1, -1)
    
    # Convert to confidence (0-1): use tanh of absolute value to map to 0-1 range
    # tanh maps [0, inf) to [0, 1), giving higher confidence for larger absolute predictions
    confidence = np.tanh(np.abs(predictions))
    
    # Calculate chop_signal: binary_prediction * confidence
    # This gives values in range [-1, 1] where magnitude represents confidence
    chop_signal = binary_prediction * confidence
    
    # Fill in predictions for valid indices
    data.loc[data.index[valid_indices], 'chop_signal'] = chop_signal
    
    return data

def save_model(model: GradientBoostingRegressor, path: str) -> None:
    path = _resolve_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, path)
    print(f"Model saved to {path}")


def load_model(path: str, df: pd.DataFrame) -> GradientBoostingRegressor:
    path = _resolve_path(path)
    if not path.exists():
        return train_chop_gbt(df)
    return joblib.load(path)