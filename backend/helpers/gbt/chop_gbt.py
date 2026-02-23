import numpy as np
import pandas as pd
from typing import Tuple
from sklearn.ensemble import GradientBoostingRegressor
import os
from .gbt_helper import create_sequences, create_sequences_with_weights, SEQUENCE_LENGTH, _resolve_path, _feature_columns
import joblib

features = [
    'open',
    'high',
    'low',
    'close',
    'volume',
    'dist_to_val',
    'dist_to_vah',
    'dist_to_vwap',
    'upper_wick',
    'lower_wick',
    'wick_ratio',
    'dir',
    'persistence_5',
    'stretch_3',
]

def train_chop_gbt(data: pd.DataFrame, model_dir: str = "trained_models") -> GradientBoostingRegressor:
    """
    Train GBT model on sequences.
    
    Args:
        data: DataFrame with all features including 'ForwardReturn'
        model_dir: Directory to save model (default: "trained_models")
    
    # Returns:
        Trained GradientBoostingRegressor model
    
    Raises:
        ValueError: If no valid training data after removing NaNs
    """
    save_path = f"{model_dir}/chop_gbt_model.pkl"
    
    # Check if regime column exists, if not use uniform weights
    use_regime_weights = 'regime' in data.columns
    
    if use_regime_weights:
        # Create sequences with regime-based weights (target regime = 1.0 for chop)
        X_sequences, y_targets, sample_weights = create_sequences_with_weights(
            data, 
            regime_col='regime',
            target_regime=1.0,  # Chop model specializes in regime 1
            weight_power=1.0     # Linear weighting (can be adjusted)
        )
        print(f"Using regime-based weighting for chop model:")
        print(f"  Weight stats: min={sample_weights.min():.3f}, mean={sample_weights.mean():.3f}, max={sample_weights.max():.3f}")
        print(f"  Weighted samples: {np.sum(sample_weights > 0.5)}/{len(sample_weights)} with weight > 0.5")
    else:
        # Fallback to uniform weights if regime not available
        X_sequences, y_targets = create_sequences(data)
        sample_weights = np.ones(len(y_targets))
        print("Warning: Regime column not found, using uniform weights for chop model")
    
    # Remove NaN targets (from forward-looking calculation)
    valid_mask = ~np.isnan(y_targets)
    X_sequences = X_sequences[valid_mask]
    y_targets = y_targets[valid_mask]
    sample_weights = sample_weights[valid_mask]
    
    # Also remove any rows with NaN in features
    feature_nan_mask = ~np.isnan(X_sequences).any(axis=1)
    X_sequences = X_sequences[feature_nan_mask]
    y_targets = y_targets[feature_nan_mask]
    sample_weights = sample_weights[feature_nan_mask]
    
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
        # Fit with sample weights to emphasize chop regime samples
        model.fit(X_sequences, y_targets, sample_weight=sample_weights)
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
    # Exclude forward-looking target cols and signal cols to match training features.
    # _feature_columns already excludes forward_return/target; also exclude signals
    # that are added by other predict functions and weren't present during training.
    signal_cols = {'trend_signal', 'chop_signal'}
    feature_cols = _feature_columns(data, extra_exclude=signal_cols)
    feature_data = data[feature_cols].values
    
    # Create sequences for prediction (matching create_sequences format)
    X_sequences = []
    valid_indices = []
    
    # Create sliding windows starting from SEQUENCE_LENGTH
    for i in range(SEQUENCE_LENGTH, len(data)):
        feature_sequence = feature_data[i - SEQUENCE_LENGTH:i]
        if np.isnan(feature_sequence).any():
            continue
        flattened_sequence = feature_sequence.flatten()
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