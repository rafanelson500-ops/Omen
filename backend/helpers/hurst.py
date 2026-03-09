import numpy as np
import pandas as pd
from numba import njit


@njit(cache=True)
def _hurst_single(ts):
    """Compute Hurst exponent for a single window using R/S method via polyfit."""
    n_lags = 18  # lags 2..19
    log_lags = np.empty(n_lags)
    log_tau  = np.empty(n_lags)

    for k in range(n_lags):
        lag = k + 2  # lag in [2, 19]
        log_lags[k] = np.log(lag)

        diff = ts[lag:] - ts[:-lag]
        # compute std of diff manually (ddof=0)
        n = len(diff)
        mean = 0.0
        for v in diff:
            mean += v
        mean /= n
        var = 0.0
        for v in diff:
            d = v - mean
            var += d * d
        var /= n
        log_tau[k] = 0.5 * np.log(var)   # log(sqrt(std)) == 0.5*log(var)

    # polyfit degree-1: slope = (n*Sxy - Sx*Sy) / (n*Sxx - Sx^2)
    n = n_lags
    sx = 0.0; sy = 0.0; sxx = 0.0; sxy = 0.0
    for i in range(n):
        sx  += log_lags[i]
        sy  += log_tau[i]
        sxx += log_lags[i] * log_lags[i]
        sxy += log_lags[i] * log_tau[i]
    slope = (n * sxy - sx * sy) / (n * sxx - sx * sx)
    return slope * 2.0


@njit(cache=True, parallel=False)
def _rolling_hurst_core(arr, window):
    n = len(arr)
    out = np.empty(n)
    for i in range(n):
        if i < window:
            out[i] = np.nan
        else:
            out[i] = _hurst_single(arr[i - window:i])
    return out


def rolling_hurst(series, window=100):
    arr = series.to_numpy(dtype=np.float64)
    result = _rolling_hurst_core(arr, window)
    return pd.Series(result, index=series.index)
