import numpy as np
import pandas as pd
from typing import Tuple
from pathlib import Path

SEQUENCE_LENGTH = 100

_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent

def _resolve_path(path: str) -> Path:
    """Resolve path relative to backend root if not absolute."""
    p = Path(path)
    return p if p.is_absolute() else (_BACKEND_ROOT / path).resolve()

def create_sequences(data: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray]:
    print(data.columns)
    feature_data = data.values
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
        # Target is the next candle's ForwardReturn value
        y_targets.append(targets[i])
    
    return np.array(X_sequences), np.array(y_targets)