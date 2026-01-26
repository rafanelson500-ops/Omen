import pandas as pd
import numpy as np
from sklearn.ensemble import GradientBoostingRegressor
import joblib
from typing import Tuple

def create_sequences(data: pd.DataFrame, sequence_length: int = 10) -> Tuple[np.ndarray, np.ndarray]:
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
    for i in range(sequence_length, len(data)):
        # Get sequence of previous candles
        sequence = feature_data[i - sequence_length:i]
        # Flatten the sequence into a single feature vector
        flattened_sequence = sequence.flatten()
        X_sequences.append(flattened_sequence)
        # Target is the next candle's ForwardReturn value
        y_targets.append(targets[i])
    
    return np.array(X_sequences), np.array(y_targets)

def train_gbt(data: pd.DataFrame, sequence_length: int = 10) -> Tuple[GradientBoostingRegressor, int]:
    """
    Train GBT model on sequences.
    
    Args:
        data: DataFrame with all features including 'ForwardReturn'
        sequence_length: Number of previous candles to use in each sequence
    
    Returns:
        Tuple of (trained_model, sequence_length)
    """
    # Create sequences from data
    X_sequences, y_targets = create_sequences(data, sequence_length)
    
    # Remove NaN targets (from forward-looking calculation)
    valid_mask = ~np.isnan(y_targets)
    X_sequences = X_sequences[valid_mask]
    y_targets = y_targets[valid_mask]
    
    model = GradientBoostingRegressor(
        n_estimators=50,
        learning_rate=0.1,
        max_depth=5,
        random_state=40,
        verbose=1
    )
    model.fit(X_sequences, y_targets)
    return model, sequence_length

def predict_next_candle(model, sequence: pd.DataFrame, sequence_length: int = 10) -> Tuple[float, float]:
    """
    Predict the ForwardReturn of the next candle given a sequence of previous candles.
    
    Args:
        model: Trained GradientBoostingRegressor model
        sequence: DataFrame with sequence_length rows of features (excluding 'ForwardReturn', 'IsGreen')
        sequence_length: Number of candles in the sequence (must match training)
    
    Returns:
        Tuple of (predicted_return, confidence) where confidence is based on magnitude
    """
    # Get feature columns (exclude target columns if present)
    feature_cols = [col for col in sequence.columns if col not in ['ForwardReturn', 'IsGreen']]
    feature_data = sequence[feature_cols].values
    
    # Ensure we have the right sequence length
    if len(feature_data) != sequence_length:
        raise ValueError(f"Sequence must have exactly {sequence_length} rows, got {len(feature_data)}")
    
    # Flatten the sequence
    flattened_sequence = feature_data.flatten().reshape(1, -1)
    
    # Predict return
    predicted_return = float(model.predict(flattened_sequence)[0])
    
    # Confidence based on magnitude (absolute value of predicted return)
    # Scale to 0-1 range (assuming returns are typically in -0.1 to 0.1 range for 1-minute candles)
    confidence = min(1.0, abs(predicted_return) * 10)  # Scale factor can be adjusted
    
    return predicted_return, confidence

def predict_with_confidence(model, data: pd.DataFrame, sequence_length: int = 10,
                            min_return_threshold: float = 0.0) -> pd.DataFrame:
    """
    Predict ForwardReturn and confidence for each candle using sequences.
    
    Args:
        model: Trained GradientBoostingRegressor model
        data: DataFrame with all features including 'ForwardReturn'
        sequence_length: Number of previous candles to use in each sequence
        min_return_threshold: Minimum return to consider a "buy" signal (default 0.0)
    
    Returns:
        DataFrame with 'PredictedReturn', 'Confidence', and 'Signal' columns added
    """
    feature_cols = [col for col in data.columns if col not in ['ForwardReturn', 'IsGreen']]
    feature_data = data[feature_cols]
    
    predictions = []
    confidences = []
    
    # For each candle starting from sequence_length, use previous candles as sequence
    for i in range(sequence_length, len(data)):
        sequence = feature_data.iloc[i - sequence_length:i]
        pred_return, conf = predict_next_candle(model, sequence, sequence_length)
        predictions.append(pred_return)
        confidences.append(conf)
    
    # Create result DataFrame
    result = data.copy()
    result['PredictedReturn'] = np.nan
    result['Confidence'] = np.nan
    result['Signal'] = 0  # 1 for buy, -1 for sell, 0 for hold
    
    # Fill in predictions (starting from sequence_length index)
    result.iloc[sequence_length:, result.columns.get_loc('PredictedReturn')] = predictions
    result.iloc[sequence_length:, result.columns.get_loc('Confidence')] = confidences
    
    # Generate signals based on predicted return and threshold
    result['Signal'] = np.where(
        result['PredictedReturn'] > min_return_threshold, 1,
        np.where(result['PredictedReturn'] < -min_return_threshold, -1, 0)
    )
    
    return result

def save_model(model: GradientBoostingRegressor, path: str, sequence_length: int = 10) -> None:
    """
    Save the GBT model and sequence length.
    
    Args:
        model: Trained GradientBoostingRegressor model
        path: Path to save the model
        sequence_length: Sequence length used during training
    """
    model_data = {
        'model': model,
        'sequence_length': sequence_length
    }
    joblib.dump(model_data, path)
    print(f"Model saved to {path}")

def load_model(path: str) -> Tuple[GradientBoostingRegressor, int]:
    """
    Load the GBT model and sequence length.
    
    Args:
        path: Path to the saved model
    
    Returns:
        Tuple of (model, sequence_length)
    """
    model_data = joblib.load(path)
    if isinstance(model_data, dict) and 'model' in model_data:
        return model_data['model'], model_data['sequence_length']
    else:
        # Backward compatibility: if it's just a model, assume default sequence_length
        return model_data, 10