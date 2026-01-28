import pandas as pd
import numpy as np
from sklearn.ensemble import GradientBoostingRegressor
import joblib
from config.config import SEQUENCE_LENGTH
from typing import Tuple

def create_sequences(data: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray]:
    """
    Create sequences from the data for training.
    
    Args:
        data: DataFrame with all features including 'ForwardReturn'
        sequence_length: Number of previous candles to use in each sequence
    
    Returns:
        Tuple of (X_sequences, y_targets) where:
        - X_sequences: Array of shape (n_samples, sequence_length * n_features)
        - y_targets: Array of shape (n_samples,) with ForwardReturn values
    """
    feature_cols = [col for col in data.columns if col not in ['ForwardReturn', 'IsGreen']]
    feature_data = data[feature_cols].values
    targets = data['ForwardReturn'].values
    
    X_sequences = []
    y_targets = []
    
    # Create sliding windows
    for i in range(SEQUENCE_LENGTH, len(data)):
        # Get sequence of previous candles
        sequence = feature_data[i - SEQUENCE_LENGTH:i]
        # Flatten the sequence into a single feature vector
        flattened_sequence = sequence.flatten()
        X_sequences.append(flattened_sequence)
        # Target is the next candle's ForwardReturn value
        y_targets.append(targets[i])
    
    return np.array(X_sequences), np.array(y_targets)

def train_gbt(data: pd.DataFrame) -> Tuple[GradientBoostingRegressor, int]:
    """
    Train GBT model on sequences.
    
    Args:
        data: DataFrame with all features including 'ForwardReturn'
        sequence_length: Number of previous candles to use in each sequence
    
    Returns:
        Tuple of (trained_model, sequence_length)
    
    Raises:
        ValueError: If no valid training data after removing NaNs
    """
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
        return model
    except ValueError as e:
        if "NaN" in str(e) or "missing values" in str(e).lower():
            raise ValueError(f"Training failed due to NaN values in features. "
                           f"Valid samples: {len(X_sequences)}, "
                           f"Features with NaN: {np.isnan(X_sequences).sum(axis=0)}") from e
        raise

def predict_next_candle(model, sequence: pd.DataFrame) -> Tuple[float, float, float, float]:
    """
    Predict the ForwardReturn distribution for the next TARGET bars given a sequence of previous candles.
    Generates a probability distribution by collecting predictions from all trees in the ensemble.
    
    Args:
        model: Trained GradientBoostingRegressor model
        sequence: DataFrame with sequence_length rows of features (excluding 'ForwardReturn', 'IsGreen')
    
    Returns:
        Tuple of (Q1, Q2/median, Q3, mean) where:
        - Q1: 25th percentile of the distribution
        - Q2: 50th percentile (median) of the distribution
        - Q3: 75th percentile of the distribution
        - mean: Mean of the distribution (standard ensemble prediction)
    """
    # Get feature columns (exclude target columns if present)
    feature_cols = [col for col in sequence.columns if col not in ['ForwardReturn', 'IsGreen']]
    feature_data = sequence[feature_cols].values
    
    # Ensure we have the right sequence length
    if len(feature_data) != SEQUENCE_LENGTH:
        raise ValueError(f"Sequence must have exactly {SEQUENCE_LENGTH} rows, got {len(feature_data)}")
    
    # Flatten the sequence
    flattened_sequence = feature_data.flatten().reshape(1, -1)
    
    # Get predictions from each tree (each tree predicts the residual)
    # We'll accumulate them progressively to build a distribution
    cumulative_predictions = []
    current_pred = model.init_.predict(flattened_sequence)[0]  # Initial prediction (usually mean)
    
    for i, tree_list in enumerate(model.estimators_):
        # For regression, tree_list has one tree
        tree = tree_list[0]
        tree_pred = tree.predict(flattened_sequence)[0]
        # Accumulate: each tree adds its prediction scaled by learning rate
        current_pred += model.learning_rate * tree_pred
        cumulative_predictions.append(float(current_pred))
    
    # Calculate quartiles from the distribution of cumulative predictions
    distribution = np.array(cumulative_predictions)
    q1 = float(np.percentile(distribution, 25))
    q2 = float(np.percentile(distribution, 50))  # Median
    q3 = float(np.percentile(distribution, 75))
    mean_pred = float(model.predict(flattened_sequence)[0])  # Standard ensemble mean
    
    return q1, q2, q3, mean_pred

def predict_with_quartiles(model, data: pd.DataFrame,
                           min_return_threshold: float = 0.0) -> pd.DataFrame:
    """
    Predict ForwardReturn distribution (quartiles) for each candle using sequences.
    Generates probability distributions for percent change over the next TARGET bars.
    
    Args:
        model: Trained GradientBoostingRegressor model
        data: DataFrame with all features including 'ForwardReturn'
        min_return_threshold: Minimum return to consider a "buy" signal (default 0.0)
    
    Returns:
        DataFrame with 'PredictedReturn_Q1', 'PredictedReturn_Q2', 'PredictedReturn_Q3', 
        'PredictedReturn' (mean), and 'Signal' columns added
    """
    feature_cols = [col for col in data.columns if col not in ['ForwardReturn', 'IsGreen']]
    feature_data = data[feature_cols]
    
    q1_predictions = []
    q2_predictions = []
    q3_predictions = []
    mean_predictions = []
    
    # For each candle starting from SEQUENCE_LENGTH, use previous candles as sequence
    for i in range(SEQUENCE_LENGTH, len(data)):
        sequence = feature_data.iloc[i - SEQUENCE_LENGTH:i]
        q1, q2, q3, mean = predict_next_candle(model, sequence)
        q1_predictions.append(q1)
        q2_predictions.append(q2)
        q3_predictions.append(q3)
        mean_predictions.append(mean)
    
    # Create result DataFrame
    result = data.copy()
    result['PredictedReturn_Q1'] = np.nan
    result['PredictedReturn_Q2'] = np.nan
    result['PredictedReturn_Q3'] = np.nan
    result['PredictedReturn'] = np.nan
    result['Signal'] = 0  # 1 for buy, -1 for sell, 0 for hold
    
    # Fill in predictions (starting from SEQUENCE_LENGTH index)
    result.iloc[SEQUENCE_LENGTH:, result.columns.get_loc('PredictedReturn_Q1')] = q1_predictions
    result.iloc[SEQUENCE_LENGTH:, result.columns.get_loc('PredictedReturn_Q2')] = q2_predictions
    result.iloc[SEQUENCE_LENGTH:, result.columns.get_loc('PredictedReturn_Q3')] = q3_predictions
    result.iloc[SEQUENCE_LENGTH:, result.columns.get_loc('PredictedReturn')] = mean_predictions
    
    # Generate signals based on median (Q2) predicted return and threshold
    result['Signal'] = np.where(
        result['PredictedReturn_Q2'] > min_return_threshold, 1,
        np.where(result['PredictedReturn_Q2'] < -min_return_threshold, -1, 0)
    )
    
    return result