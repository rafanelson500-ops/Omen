import numpy as np
from hmmlearn import hmm
import joblib
from typing import Optional
import pandas as pd
import os

features = ['LogReturn', 'RollingMeanReturn', 'RealizedVol', 'VolOfVol', 'VolumeZ', 'ReturnZ']

def train_hmm(df: pd.DataFrame, n_components: int = 2, n_iter: int = 100, random_state: int = 42) -> hmm.GaussianHMM:
    """
    Train a Gaussian HMM model on normalized features.
    
    Args:
        features: Normalized feature array of shape (n_samples, n_features)
                  Features should be: [returns, realized_vol, autocorrelation]
        n_components: Number of hidden states (regimes)
        n_iter: Maximum number of iterations for EM algorithm
        random_state: Random seed for reproducibility
    
    Returns:
        Trained GaussianHMM model
    """
    f = df[features].values
    # Create and fit the HMM model
    model = hmm.GaussianHMM(
        n_components=n_components,
        covariance_type="full",
        n_iter=n_iter,
        random_state=random_state
    )
    
    # Fit the model
    model.fit(f)
    save_model(model, "./trained_models/regieme_model.pkl")
    
    return model


def predict_regimes(hmm_model: hmm.GaussianHMM, df: pd.DataFrame) -> np.ndarray:
    """
    Predict regimes using a trained HMM model.
    
    Args:
        hmm_model: Trained GaussianHMM model
        df: DataFrame with the required features
    
    Returns:
        Array of predicted regime labels
    """
    feature_values = df[features].values
    regimes = hmm_model.predict(feature_values)
    return regimes


def save_model(hmm_model: hmm.GaussianHMM, path: str) -> None:
    # Create directory if it doesn't exist
    os.makedirs(os.path.dirname(path), exist_ok=True)
    joblib.dump(hmm_model, path)
    print(f"Model saved to {path}")


def load_model(path: str) -> hmm.GaussianHMM:
    model = joblib.load(path)
    return model