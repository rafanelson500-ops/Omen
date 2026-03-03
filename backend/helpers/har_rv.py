import numpy as np
import pandas as pd
from scipy import linalg


def _ols_regression(y, X):
    """
    Ordinary Least Squares regression using numpy.
    
    Parameters
    ----------
    y : np.ndarray
        Dependent variable (n_samples,)
    X : np.ndarray
        Independent variables (n_samples, n_features)
    
    Returns
    -------
    coefficients : np.ndarray
        Regression coefficients (n_features,)
    predicted : np.ndarray
        Predicted values (n_samples,)
    """
    # Add intercept column
    X_with_intercept = np.column_stack([np.ones(len(X)), X])
    
    # Solve normal equations: (X'X)^(-1)X'y
    try:
        coeffs = linalg.lstsq(X_with_intercept, y)[0]
        predicted = X_with_intercept @ coeffs
        return coeffs, predicted
    except (linalg.LinAlgError, ValueError):
        # Return zeros if regression fails (singular matrix, etc.)
        return np.zeros(X_with_intercept.shape[1]), np.zeros(len(y))


def add_har_rv(df: pd.DataFrame, rolling_window: int = 500, min_samples: int = 100) -> pd.DataFrame:
    """
    Adds HAR-RV (Heterogeneous Autoregressive Realized Variance) features using a proper
    regression model following Corsi (2009).
    
    The HAR-RV model predicts realized variance using lagged components at different horizons:
    RV_{t+1} = β₀ + β₁·RV_t^{5m} + β₂·RV_t^{30m} + β₃·RV_t^{1d} + ε_t
    
    A rolling window OLS regression is used to estimate coefficients, making the model
    adaptive to changing volatility regimes.
    
    Parameters
    ----------
    df : pd.DataFrame
        Must contain a "close" column with a datetime index.
        Assumes 5-minute bars.
    rolling_window : int, default=500
        Number of bars to use for rolling regression estimation (500 bars ≈ 2 days).
    min_samples : int, default=100
        Minimum number of samples required before computing regression predictions.
    
    Returns
    -------
    pd.DataFrame
        Original dataframe with added columns:
        - har_rv_5m:      Current bar's squared log return (1 bar = 5 minutes)
        - har_rv_30m:     Rolling 6-bar mean of squared log returns (6 bars = 30 minutes)
        - har_rv_1d:      Rolling 288-bar mean of squared log returns (288 bars = 24 hours)
        - har_rv_pred:    Predicted realized variance from HAR-RV regression model
        - har_rv_coef_0:  Regression intercept (β₀)
        - har_rv_coef_1:  Coefficient for 5m component (β₁)
        - har_rv_coef_2:  Coefficient for 30m component (β₂)
        - har_rv_coef_3:  Coefficient for 1d component (β₃)
    
    References
    ----------
    Corsi, F. (2009). A simple approximate long-memory model of realized volatility.
    Journal of Financial Econometrics, 7(2), 174-196.
    """
    df = df.copy()

    # Compute log returns
    log_ret = np.log(df["close"] / df["close"].shift(1))

    # Per-bar realized variance proxy (squared log return)
    rv = log_ret ** 2

    # HAR-RV components at different horizons (lagged by 1 period for prediction)
    rv_5m = rv                                    # 1 bar  =  5 minutes
    rv_30m = rv.rolling(6).mean()                 # 6 bars = 30 minutes
    rv_1d = rv.rolling(288).mean()                # 288 bars = 24 hours (1 day)
    
    # Store components
    df["har_rv_5m"] = rv_5m
    df["har_rv_30m"] = rv_30m
    df["har_rv_1d"] = rv_1d

    # Prepare feature matrix: lagged RV components
    # We predict RV_t using RV_{t-1} components (no look-ahead bias)
    X = np.column_stack([
        rv_5m.shift(1).values,   # RV_{t-1}^{5m}
        rv_30m.shift(1).values,  # RV_{t-1}^{30m}
        rv_1d.shift(1).values,   # RV_{t-1}^{1d}
    ])
    y = rv.values  # Target: RV_t (we're predicting current RV from lagged components)

    # Pre-allocate result arrays for better performance
    n = len(df)
    har_rv_pred = np.full(n, np.nan, dtype=np.float64)
    har_rv_coef_0 = np.full(n, np.nan, dtype=np.float64)
    har_rv_coef_1 = np.full(n, np.nan, dtype=np.float64)
    har_rv_coef_2 = np.full(n, np.nan, dtype=np.float64)
    har_rv_coef_3 = np.full(n, np.nan, dtype=np.float64)

    # Rolling window regression
    for i in range(min_samples, n):
        # Get rolling window indices
        start_idx = max(0, i - rolling_window)
        end_idx = i
        
        # Extract window data
        X_window = X[start_idx:end_idx]
        y_window = y[start_idx:end_idx]
        
        # Remove rows with NaN (from lagging)
        valid_mask = ~(np.isnan(X_window).any(axis=1) | np.isnan(y_window))
        if valid_mask.sum() < 10:  # Need at least 10 valid samples
            continue
            
        X_valid = X_window[valid_mask]
        y_valid = y_window[valid_mask]
        
        # Fit OLS regression
        coeffs, _ = _ols_regression(y_valid, X_valid)
        
        # Predict current period's RV using lagged components (X[i] contains lagged features)
        if not np.isnan(X[i]).any():
            X_current = X[i:i+1]
            X_with_intercept = np.column_stack([np.ones(1), X_current])
            pred_value = (X_with_intercept @ coeffs)[0]
            har_rv_pred[i] = pred_value
        
        # Store coefficients
        har_rv_coef_0[i] = coeffs[0]  # intercept
        har_rv_coef_1[i] = coeffs[1]  # 5m
        har_rv_coef_2[i] = coeffs[2]  # 30m
        har_rv_coef_3[i] = coeffs[3]  # 1d
    
    # Assign results back to dataframe (much faster than iloc)
    df["har_rv_pred"] = har_rv_pred
    df["har_rv_coef_0"] = har_rv_coef_0
    df["har_rv_coef_1"] = har_rv_coef_1
    df["har_rv_coef_2"] = har_rv_coef_2
    df["har_rv_coef_3"] = har_rv_coef_3

    return df
