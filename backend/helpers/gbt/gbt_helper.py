import numpy as np
import pandas as pd
from typing import Tuple
from pathlib import Path

SEQUENCE_LENGTH = 100

# Columns that must never appear in model input features.
# forward_return / target are forward-looking labels that change as new candles
# arrive, so including them causes historical predictions to shift.
_EXCLUDE_FROM_FEATURES = {'forward_return', 'target'}

_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent

def _resolve_path(path: str) -> Path:
    """Resolve path relative to backend root if not absolute."""
    p = Path(path)
    return p if p.is_absolute() else (_BACKEND_ROOT / path).resolve()

def _feature_columns(data: pd.DataFrame, extra_exclude: set | None = None) -> list[str]:
    """Return column names safe to use as model input features."""
    exclude = _EXCLUDE_FROM_FEATURES | (extra_exclude or set())
    return [c for c in data.columns if c not in exclude]

def create_sequences(data: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray]:
    feature_cols = _feature_columns(data)
    feature_data = data[feature_cols].values
    targets = data['target'].values
    
    X_sequences = []
    y_targets = []
    
    # Create sliding windows
    for i in range(SEQUENCE_LENGTH, len(data)):
        # Get sequence of previous candles
        sequence = feature_data[i - SEQUENCE_LENGTH:i]
        # Flatten the sequence into a single feature vector
        flattened_sequence = sequence.flatten()
        X_sequences.append(flattened_sequence)
        # Target is the next candle's target value
        y_targets.append(targets[i])
    
    return np.array(X_sequences), np.array(y_targets)

def create_sequences_with_weights(
    data: pd.DataFrame, 
    regime_col: str = 'regime',
    target_regime: float = 0.0,
    weight_power: float = 1.0
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Create sequences with sample weights based on regime distance.
    
    Args:
        data: DataFrame with all features including 'target' and regime column
        regime_col: Name of the regime column (default: 'regime')
        target_regime: Target regime value (0.0 for trend, 1.0 for chop)
        weight_power: Power to raise the weight (1.0 = linear, 2.0 = squared, etc.)
                     Higher values create sharper focus on target regime
    
    Returns:
        Tuple of (X_sequences, y_targets, sample_weights)
    """
    feature_cols = _feature_columns(data)
    feature_data = data[feature_cols].values
    targets = data['target'].values
    
    # Get regime values if available
    if regime_col not in data.columns:
        # If regime not available, use uniform weights
        regimes = np.ones(len(data)) * 0.5  # Neutral regime
    else:
        regimes = data[regime_col].values
    
    X_sequences = []
    y_targets = []
    sample_weights = []
    
    # Create sliding windows
    for i in range(SEQUENCE_LENGTH, len(data)):
        # Get sequence of previous candles
        sequence = feature_data[i - SEQUENCE_LENGTH:i]
        # Flatten the sequence into a single feature vector
        flattened_sequence = sequence.flatten()
        X_sequences.append(flattened_sequence)
        # Target is the current candle's target value
        y_targets.append(targets[i])
        
        # Calculate weight based on regime distance from target
        # Use regime at prediction point (index i) - most relevant for prediction
        regime_at_i = regimes[i]
        
        # Handle NaN regime values (use neutral weight of 0.5)
        if np.isnan(regime_at_i):
            weight = 0.5
        else:
            # Calculate distance from target regime
            # For trend (target=0): weight = 1 - regime, higher when regime closer to 0
            # For chop (target=1): weight = regime, higher when regime closer to 1
            if target_regime == 0.0:
                # Trend model: weight decreases as regime increases
                weight = 1.0 - regime_at_i
            elif target_regime == 1.0:
                # Chop model: weight increases as regime increases
                weight = regime_at_i
            else:
                # Generic: weight based on distance from target
                weight = 1.0 - abs(regime_at_i - target_regime)
        
        # Apply power to create sharper or softer focus
        # Clamp to [0, 1] and raise to power
        weight = np.clip(weight, 0.0, 1.0) ** weight_power
        
        sample_weights.append(weight)
    
    return np.array(X_sequences), np.array(y_targets), np.array(sample_weights)