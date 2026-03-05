import numpy as np
import pandas as pd
from scipy import linalg

def add_har_rv(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    
    log_ret = np.log(df["close"] / df["close"].shift(1))
    
    # Zero out log returns at session boundaries to exclude aftermarket moves
    if "new_session" in df.columns:
        log_ret = log_ret.where(df["new_session"] != 1, 0)

    # Per-bar realized variance proxy (squared log return)
    rv = log_ret ** 2

    # HAR-RV components at different horizons (lagged by 1 period for prediction)
    rv_short = rv.shift(24)                           # 1 bar  =  5 minutes (lagged)
    rv_medium = rv.rolling(288).mean().shift(1)        # 6 bars = 30 minutes (lagged)
    rv_long = rv.rolling(864).mean().shift(1)         # 24 bars = 2 hours (lagged)
    
    # Prepare data for regression: drop rows with NaN values
    valid_mask = ~(rv.isna() | rv_short.isna() | rv_medium.isna() | rv_long.isna())
    
    # Create feature matrix X (with intercept) and target y
    X = np.column_stack([
        np.ones(np.sum(valid_mask)),  # intercept
        rv_short[valid_mask].values,
        rv_medium[valid_mask].values,
        rv_long[valid_mask].values
    ])
    y = rv[valid_mask].values
    
    # Fit HAR-RV model using least squares
    # Model: RV_t = β₀ + β₁*RV_{t-1} + β₂*RV_{t-1}^{medium} + β₃*RV_{t-1}^{long}
    coeffs, _, _, _ = linalg.lstsq(X, y)
    
    # Generate predictions for all rows
    X_all = np.column_stack([
        np.ones(len(df)),
        rv_short.values,
        rv_medium.values,
        rv_long.values
    ])
    
    # Predict har_rv using fitted coefficients
    har_rv_pred = X_all @ coeffs
    
    # Add har_rv column to dataframe
    df["har_rv"] = har_rv_pred
    
    return df
