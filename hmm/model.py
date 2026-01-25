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
    regimes = hmm_model.predict(features)
    return regimes


def save_model(hmm_model: hmm.GaussianHMM, path: str) -> None:
    joblib.dump(hmm_model, path)
    print(f"Model saved to {path}")


def load_model(path: str) -> hmm.GaussianHMM:
    model = joblib.load(path)
    return model