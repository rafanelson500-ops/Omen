"""
Hidden Markov Model for regime detection.
Uses hmmlearn to identify 3 market regimes based on returns, volatility, and autocorrelation.
"""

import numpy as np
from hmmlearn import hmm
import joblib
from typing import Optional


def train_hmm(features: np.ndarray, n_components: int = 3, n_iter: int = 100, random_state: int = 42) -> hmm.GaussianHMM:
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
    # Create and fit the HMM model
    model = hmm.GaussianHMM(
        n_components=n_components,
        covariance_type="full",
        n_iter=n_iter,
        random_state=random_state
    )
    
    # Fit the model
    model.fit(features)
    
    return model


def predict_regimes(hmm_model: hmm.GaussianHMM, features: np.ndarray) -> np.ndarray:
    """
    Predict regime states for given features.
    
    Args:
        hmm_model: Trained GaussianHMM model
        features: Normalized feature array of shape (n_samples, n_features)
    
    Returns:
        Array of predicted regime labels (0, 1, 2, ...)
    """
    regimes = hmm_model.predict(features)
    return regimes


def save_model(hmm_model: hmm.GaussianHMM, path: str) -> None:
    """
    Save trained HMM model to disk.
    
    Args:
        hmm_model: Trained GaussianHMM model
        path: File path to save the model
    """
    joblib.dump(hmm_model, path)
    print(f"Model saved to {path}")


def load_model(path: str) -> hmm.GaussianHMM:
    """
    Load HMM model from disk.
    
    Args:
        path: File path to load the model from
    
    Returns:
        Loaded GaussianHMM model
    """
    model = joblib.load(path)
    return model
