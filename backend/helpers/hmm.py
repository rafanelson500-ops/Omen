import numpy as np
from hmmlearn import hmm
import joblib
from pathlib import Path
from typing import Optional
import pandas as pd

# Backend root (parent of helpers/) so paths work from any CWD
_BACKEND_ROOT = Path(__file__).resolve().parent.parent

features = ['log_return', 'rolling_mean_return', 'realized_vol', 'vol_of_vol', 'volume_z', 'return_z']

def _resolve_path(path: str) -> Path:
    """Resolve path relative to backend root if not absolute."""
    p = Path(path)
    return p if p.is_absolute() else (_BACKEND_ROOT / path).resolve()

def train_hmm(df: pd.DataFrame, n_components: int = 2, n_iter: int = 100, random_state: int = 42,
              model_dir: Optional[str] = None) -> hmm.GaussianHMM:
    """
    Train a Gaussian HMM model on normalized features.
    
    Args:
        df: DataFrame with required features
        n_components: Number of hidden states (regimes)
        n_iter: Maximum number of iterations for EM algorithm
        random_state: Random seed for reproducibility
        model_dir: Directory to save model (default: backend/trained_models)
    
    Returns:
        Trained GaussianHMM model
    """
    base = Path(model_dir) if model_dir else _BACKEND_ROOT / "trained_models"
    save_path = _resolve_path(str(base)) / "regime_model.pkl"
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

    realized_vol_idx = features.index('realized_vol')
    state_vols = model.means_[:, realized_vol_idx]
    
    # If state 0 has lower vol than state 1, swap the states
    if state_vols[0] > state_vols[1]:
        # Swap means
        model.means_ = model.means_[[1, 0], :]
        # Swap covariances
        model.covars_ = model.covars_[[1, 0], :]
        # Swap start probabilities
        model.startprob_ = model.startprob_[[1, 0]]
        # Swap transition matrix (both rows and columns)
        model.transmat_ = model.transmat_[[1, 0], :][:, [1, 0]]

    save_model(model, str(save_path))
    
    return model


def predict_regimes(hmm_model: hmm.GaussianHMM, df: pd.DataFrame) -> np.ndarray:
    """
    Predict regime confidence scores using a trained HMM model.
    
    Uses forward-only filtering so that each candle's regime probability
    depends only on past and present observations, never future ones.
    This prevents historical regime values from changing when new candles arrive.
    
    Args:
        hmm_model: Trained GaussianHMM model
        df: DataFrame with the required features
    
    Returns:
        Array of regime confidence scores between 0 and 1.
        Closer to 0 means closer to regime label 0.
        Closer to 1 means closer to regime label 1.
    """
    feature_values = df[features].values
    posteriors = _forward_only_probabilities(hmm_model, feature_values)
    
    # For a 2-state model, posteriors[:, 1] gives the probability of being in state 1
    # This serves as our confidence score (0 = regime 0, 1 = regime 1)
    regime_confidence = posteriors[:, 1]
    
    return regime_confidence


def _forward_only_probabilities(model: hmm.GaussianHMM, X: np.ndarray) -> np.ndarray:
    """
    Compute filtering probabilities P(state_t | obs_1:t) using forward algorithm only.
    
    Unlike score_samples (forward-backward), this only uses past/present observations
    so adding future data cannot change historical probabilities.
    """
    framelogprob = model._compute_log_likelihood(X)
    n_samples, n_components = framelogprob.shape

    log_startprob = np.log(model.startprob_ + 1e-300)
    log_transmat = np.log(model.transmat_ + 1e-300)

    # Forward pass in log space
    fwdlattice = np.zeros((n_samples, n_components))

    # t = 0: prior * emission
    fwdlattice[0] = log_startprob + framelogprob[0]

    # t = 1 .. T-1
    for t in range(1, n_samples):
        for j in range(n_components):
            fwdlattice[t, j] = (
                np.logaddexp.reduce(fwdlattice[t - 1] + log_transmat[:, j])
                + framelogprob[t, j]
            )

    # Normalize each row to get P(state_t | obs_1:t)
    log_normalizer = np.logaddexp.reduce(fwdlattice, axis=1, keepdims=True)
    posteriors = np.exp(fwdlattice - log_normalizer)

    return posteriors


def save_model(hmm_model: hmm.GaussianHMM, path: str) -> None:
    path = _resolve_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(hmm_model, path)
    print(f"Model saved to {path}")


def load_model(path: str, df: pd.DataFrame) -> hmm.GaussianHMM:
    path = _resolve_path(path)
    if not path.exists():
        return train_hmm(df, model_dir = str(path.parent))
    return joblib.load(path)