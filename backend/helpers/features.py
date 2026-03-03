import numpy as np
import pandas as pd
import time
from scipy.stats import kurtosis
from helpers.har_rv import add_har_rv


def add_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Adds regime-predictive features to a 5-minute OHLCV dataframe.

    Features
    --------
    HAR-RV  (Heterogeneous Autoregressive Realized Variance)
        Computed via helpers.har_rv module. Decomposes realized variance across
        horizons (5m, 30m, 1d) to capture volatility clustering at different
        timescales – a key signal for regime detection.

    Rolling VWAP Deviation  (vwap_dev)
        Normalised distance of close from a 2-hour rolling VWAP.
        Large deviations signal price has overstretched from institutional
        fair value – a strong precursor of mean-reversion episodes.

    Rolling Lag-1 Return Autocorrelation  (ret_ac1)
        Pearson correlation between r_t and r_{t-1} over a 2.5-hour window.
        Negative AC1 is the statistical fingerprint of mean reversion;
        positive AC1 indicates momentum / trending.

    Variance Ratio  (variance_ratio)
        Lo-MacKinlay variance ratio VR(k) = Var(k·Δt returns) / (k·Var(Δt returns)),
        estimated over a rolling 4-hour window with k = 4 bars (20 m vs 5 m).
        VR < 1 → mean-reverting market; VR > 1 → trending market;
        VR ≈ 1 → random walk.

    Additional Mean Reversion Features:
    - Multiple variance ratios (k=2, 8, 16)
    - Hurst exponent (rolling)
    - Half-life of mean reversion
    - Z-score from moving averages (multiple windows)
    - Bollinger Band position
    - RSI (Relative Strength Index)
    - Price position in recent range
    - Rolling skewness and kurtosis
    - EMA deviation (multiple periods)
    - Stochastic oscillator (%K, %D)
    - Williams %R
    - Commodity Channel Index (CCI)
    - Detrended Price Oscillator (DPO)
    - Price distance from median
    - Multiple autocorrelations (lags 1-5)
    - ADF test statistic (rolling)
    """
    df = df.copy()

    # ── Log returns (internal; used by all features below) ───────────────────
    print("[Features] Computing log returns...")
    start_time = time.time()
    log_ret = np.log(df["close"] / df["close"].shift(1))
    print(f"[Features] Log returns computed in {time.time() - start_time:.3f}s")

    # ════════════════════════════════════════════════════════════════════════
    # 2.  Rolling VWAP Deviation
    # ════════════════════════════════════════════════════════════════════════
    print("[Features] Computing VWAP Deviation...")
    start_time = time.time()
    _vwap_window = 24                                 # 24 × 5 m = 2 h
    _typical     = (df["high"] + df["low"] + df["close"]) / 3
    _vwap        = (
        (_typical * df["volume"]).rolling(_vwap_window).sum()
        / df["volume"].rolling(_vwap_window).sum()
    )
    df["vwap_dev"] = (df["close"] - _vwap) / _vwap   # dimensionless
    print(f"[Features] VWAP Deviation computed in {time.time() - start_time:.3f}s")

    # ════════════════════════════════════════════════════════════════════════
    # 3.  Rolling Lag-1 Return Autocorrelation
    # ════════════════════════════════════════════════════════════════════════
    print("[Features] Computing Lag-1 Return Autocorrelation...")
    start_time = time.time()
    _ac_window  = 30                                  # 30 × 5 m = 2.5 h
    _ret_lag1   = log_ret.shift(1)
    _cov        = log_ret.rolling(_ac_window).cov(_ret_lag1)
    _std        = log_ret.rolling(_ac_window).std()
    _std_lag1   = _ret_lag1.rolling(_ac_window).std()
    df["ret_ac1"] = _cov / (_std * _std_lag1)
    print(f"[Features] Lag-1 Return Autocorrelation computed in {time.time() - start_time:.3f}s")

    # ════════════════════════════════════════════════════════════════════════
    # 4.  Variance Ratio  (Lo-MacKinlay, k = 4 bars = 20 m)
    # ════════════════════════════════════════════════════════════════════════
    print("[Features] Computing Variance Ratio (k=4)...")
    start_time = time.time()
    _k          = 4                                   # aggregation horizon in bars
    _vr_window  = 48                                  # 48 × 5 m = 4 h estimation window
    _ret_k      = log_ret.rolling(_k).sum()           # k-period overlapping returns
    _var1       = log_ret.rolling(_vr_window).var()
    _var_k      = _ret_k.rolling(_vr_window).var()
    df["variance_ratio"] = _var_k / (_k * _var1)
    print(f"[Features] Variance Ratio (k=4) computed in {time.time() - start_time:.3f}s")

    # ════════════════════════════════════════════════════════════════════════
    # 5.  Additional Variance Ratios (k = 2, 8, 16)
    # ════════════════════════════════════════════════════════════════════════
    print("[Features] Computing Additional Variance Ratios (k=2,8,16)...")
    start_time = time.time()
    for k in [2, 8, 16]:
        _ret_k = log_ret.rolling(k).sum()
        _var_k = _ret_k.rolling(_vr_window).var()
        df[f"variance_ratio_{k}"] = _var_k / (k * _var1)
    print(f"[Features] Additional Variance Ratios computed in {time.time() - start_time:.3f}s")

    # ════════════════════════════════════════════════════════════════════════
    # 6.  Rolling Hurst Exponent
    # ════════════════════════════════════════════════════════════════════════
    print("[Features] Computing Rolling Hurst Exponent...")
    start_time = time.time()
    _hurst_window = 100                               # 100 × 5 m ≈ 8.3 h
    def _rolling_hurst(series, window):
        """Compute rolling Hurst exponent using R/S analysis"""
        hurst = pd.Series(index=series.index, dtype=float)
        for i in range(window, len(series)):
            window_data = series.iloc[i-window:i]
            if len(window_data) < 2:
                hurst.iloc[i] = np.nan
                continue
            # R/S method
            mean = window_data.mean()
            deviations = window_data - mean
            cumsum = deviations.cumsum()
            R = cumsum.max() - cumsum.min()
            S = window_data.std()
            if S > 0:
                hurst.iloc[i] = np.log(R / S) / np.log(window)
            else:
                hurst.iloc[i] = np.nan
        return hurst
    df["hurst"] = _rolling_hurst(log_ret, _hurst_window)
    print(f"[Features] Rolling Hurst Exponent computed in {time.time() - start_time:.3f}s")

    # ════════════════════════════════════════════════════════════════════════
    # 7.  Half-Life of Mean Reversion
    # ════════════════════════════════════════════════════════════════════════
    print("[Features] Computing Half-Life of Mean Reversion...")
    start_time = time.time()
    _hl_window = 60                                   # 60 × 5 m = 5 h
    def _rolling_half_life(series, window):
        """Estimate half-life using AR(1) model: price_t = α + β·price_{t-1} + ε"""
        half_life = pd.Series(index=series.index, dtype=float)
        for i in range(window, len(series)):
            window_data = series.iloc[i-window:i]
            if len(window_data) < 2:
                half_life.iloc[i] = np.nan
                continue
            y = window_data.values[1:]
            x = window_data.values[:-1]
            try:
                beta = np.cov(x, y)[0, 1] / np.var(x)
                if beta < 1 and beta > 0:
                    half_life.iloc[i] = -np.log(2) / np.log(beta)
                else:
                    half_life.iloc[i] = np.nan
            except:
                half_life.iloc[i] = np.nan
        return half_life
    df["half_life"] = _rolling_half_life(df["close"], _hl_window)
    print(f"[Features] Half-Life of Mean Reversion computed in {time.time() - start_time:.3f}s")

    # ════════════════════════════════════════════════════════════════════════
    # 8.  Z-Score from Moving Averages (multiple windows)
    # ════════════════════════════════════════════════════════════════════════
    print("[Features] Computing Z-Score from Moving Averages...")
    start_time = time.time()
    for ma_window in [12, 24, 48, 96]:  # 1h, 2h, 4h, 8h
        ma = df["close"].rolling(ma_window).mean()
        std = df["close"].rolling(ma_window).std()
        df[f"zscore_ma{ma_window}"] = (df["close"] - ma) / std
    print(f"[Features] Z-Score from Moving Averages computed in {time.time() - start_time:.3f}s")

    # ════════════════════════════════════════════════════════════════════════
    # 9.  Bollinger Band Position
    # ════════════════════════════════════════════════════════════════════════
    print("[Features] Computing Bollinger Band Position...")
    start_time = time.time()
    _bb_window = 20                                   # 20 × 5 m = 100 m
    _bb_std = 2
    bb_mean = df["close"].rolling(_bb_window).mean()
    bb_std = df["close"].rolling(_bb_window).std()
    df["bb_upper"] = bb_mean + _bb_std * bb_std
    df["bb_lower"] = bb_mean - _bb_std * bb_std
    df["bb_position"] = (df["close"] - df["bb_lower"]) / (df["bb_upper"] - df["bb_lower"])
    print(f"[Features] Bollinger Band Position computed in {time.time() - start_time:.3f}s")

    # ════════════════════════════════════════════════════════════════════════
    # 10. RSI (Relative Strength Index)
    # ════════════════════════════════════════════════════════════════════════
    print("[Features] Computing RSI...")
    start_time = time.time()
    _rsi_window = 14                                  # 14 × 5 m = 70 m
    delta = df["close"].diff()
    gain = (delta.where(delta > 0, 0)).rolling(_rsi_window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(_rsi_window).mean()
    rs = gain / loss
    df["rsi"] = 100 - (100 / (1 + rs))
    print(f"[Features] RSI computed in {time.time() - start_time:.3f}s")

    # ════════════════════════════════════════════════════════════════════════
    # 11. Price Position in Recent Range
    # ════════════════════════════════════════════════════════════════════════
    print("[Features] Computing Price Position in Recent Range...")
    start_time = time.time()
    for range_window in [20, 40, 60]:  # 100m, 200m, 300m
        high_max = df["high"].rolling(range_window).max()
        low_min = df["low"].rolling(range_window).min()
        df[f"price_position_{range_window}"] = (df["close"] - low_min) / (high_max - low_min)
    print(f"[Features] Price Position in Recent Range computed in {time.time() - start_time:.3f}s")

    # ════════════════════════════════════════════════════════════════════════
    # 12. Rolling Skewness and Kurtosis
    # ════════════════════════════════════════════════════════════════════════
    print("[Features] Computing Rolling Skewness and Kurtosis...")
    start_time = time.time()
    _skew_window = 50                                 # 50 × 5 m ≈ 4.2 h
    df["skewness"] = log_ret.rolling(_skew_window).skew()
    df["kurtosis"] = log_ret.rolling(_skew_window).apply(lambda x: kurtosis(x, nan_policy='omit'), raw=True)
    print(f"[Features] Rolling Skewness and Kurtosis computed in {time.time() - start_time:.3f}s")

    # ════════════════════════════════════════════════════════════════════════
    # 13. EMA Deviation (multiple periods)
    # ════════════════════════════════════════════════════════════════════════
    print("[Features] Computing EMA Deviation...")
    start_time = time.time()
    for ema_period in [12, 24, 48]:
        ema = df["close"].ewm(span=ema_period, adjust=False).mean()
        df[f"ema_dev_{ema_period}"] = (df["close"] - ema) / ema
    print(f"[Features] EMA Deviation computed in {time.time() - start_time:.3f}s")

    # ════════════════════════════════════════════════════════════════════════
    # 14. Stochastic Oscillator (%K and %D)
    # ════════════════════════════════════════════════════════════════════════
    print("[Features] Computing Stochastic Oscillator...")
    start_time = time.time()
    _stoch_window = 14
    low_min = df["low"].rolling(_stoch_window).min()
    high_max = df["high"].rolling(_stoch_window).max()
    df["stoch_k"] = 100 * (df["close"] - low_min) / (high_max - low_min)
    df["stoch_d"] = df["stoch_k"].rolling(3).mean()
    print(f"[Features] Stochastic Oscillator computed in {time.time() - start_time:.3f}s")

    # ════════════════════════════════════════════════════════════════════════
    # 15. Williams %R
    # ════════════════════════════════════════════════════════════════════════
    print("[Features] Computing Williams %R...")
    start_time = time.time()
    _willr_window = 14
    high_max_wr = df["high"].rolling(_willr_window).max()
    low_min_wr = df["low"].rolling(_willr_window).min()
    df["williams_r"] = -100 * (high_max_wr - df["close"]) / (high_max_wr - low_min_wr)
    print(f"[Features] Williams %R computed in {time.time() - start_time:.3f}s")

    # ════════════════════════════════════════════════════════════════════════
    # 16. Commodity Channel Index (CCI)
    # ════════════════════════════════════════════════════════════════════════
    print("[Features] Computing Commodity Channel Index (CCI)...")
    start_time = time.time()
    _cci_window = 20
    typical_price = (df["high"] + df["low"] + df["close"]) / 3
    sma_tp = typical_price.rolling(_cci_window).mean()
    mad = typical_price.rolling(_cci_window).apply(lambda x: np.abs(x - x.mean()).mean())
    df["cci"] = (typical_price - sma_tp) / (0.015 * mad)
    print(f"[Features] Commodity Channel Index computed in {time.time() - start_time:.3f}s")

    # ════════════════════════════════════════════════════════════════════════
    # 17. Detrended Price Oscillator (DPO)
    # ════════════════════════════════════════════════════════════════════════
    print("[Features] Computing Detrended Price Oscillator (DPO)...")
    start_time = time.time()
    _dpo_period = 20
    sma_dpo = df["close"].rolling(_dpo_period).mean()
    df["dpo"] = df["close"] - sma_dpo.shift(_dpo_period // 2 + 1)
    print(f"[Features] Detrended Price Oscillator computed in {time.time() - start_time:.3f}s")

    # ════════════════════════════════════════════════════════════════════════
    # 18. Price Distance from Median
    # ════════════════════════════════════════════════════════════════════════
    print("[Features] Computing Price Distance from Median...")
    start_time = time.time()
    for med_window in [24, 48, 96]:
        median = df["close"].rolling(med_window).median()
        std = df["close"].rolling(med_window).std()
        df[f"median_dev_{med_window}"] = (df["close"] - median) / std
    print(f"[Features] Price Distance from Median computed in {time.time() - start_time:.3f}s")

    # ════════════════════════════════════════════════════════════════════════
    # 19. Multiple Autocorrelations (lags 1-5)
    # ════════════════════════════════════════════════════════════════════════
    print("[Features] Computing Multiple Autocorrelations (lags 2-5)...")
    start_time = time.time()
    _ac_window_multi = 30
    for lag in range(2, 6):
        _ret_lag = log_ret.shift(lag)
        _cov = log_ret.rolling(_ac_window_multi).cov(_ret_lag)
        _std = log_ret.rolling(_ac_window_multi).std()
        _std_lag = _ret_lag.rolling(_ac_window_multi).std()
        df[f"ret_ac{lag}"] = _cov / (_std * _std_lag)
    print(f"[Features] Multiple Autocorrelations computed in {time.time() - start_time:.3f}s")

    # ════════════════════════════════════════════════════════════════════════
    # 20. Rolling ADF Test Statistic (simplified)
    # ════════════════════════════════════════════════════════════════════════
    print("[Features] Computing Rolling ADF Test Statistic...")
    start_time = time.time()
    _adf_window = 100
    def _rolling_adf_stat(series, window):
        """Simplified ADF test statistic (regression coefficient)"""
        adf_stat = pd.Series(index=series.index, dtype=float)
        for i in range(window, len(series)):
            window_data = series.iloc[i-window:i]
            if len(window_data) < 3:
                adf_stat.iloc[i] = np.nan
                continue
            # Simplified: regress diff on lagged level
            y = np.diff(window_data.values)
            x = window_data.values[:-1]
            try:
                if np.var(x) > 1e-10:
                    beta = np.cov(x, y)[0, 1] / np.var(x)
                    adf_stat.iloc[i] = beta
                else:
                    adf_stat.iloc[i] = np.nan
            except:
                adf_stat.iloc[i] = np.nan
        return adf_stat
    df["adf_stat"] = _rolling_adf_stat(df["close"], _adf_window)
    print(f"[Features] Rolling ADF Test Statistic computed in {time.time() - start_time:.3f}s")

    # ════════════════════════════════════════════════════════════════════════
    # 21. Volume-Weighted Price Deviation
    # ════════════════════════════════════════════════════════════════════════
    print("[Features] Computing Volume-Weighted Price Deviation...")
    start_time = time.time()
    for vwap_window in [12, 24, 48]:
        typical = (df["high"] + df["low"] + df["close"]) / 3
        vwap = (typical * df["volume"]).rolling(vwap_window).sum() / df["volume"].rolling(vwap_window).sum()
        std = df["close"].rolling(vwap_window).std()
        df[f"vwap_zscore_{vwap_window}"] = (df["close"] - vwap) / std
    print(f"[Features] Volume-Weighted Price Deviation computed in {time.time() - start_time:.3f}s")

    # ════════════════════════════════════════════════════════════════════════
    # 22. Price Momentum Oscillator
    # ════════════════════════════════════════════════════════════════════════
    print("[Features] Computing Price Momentum Oscillator...")
    start_time = time.time()
    for mom_window in [10, 20, 30]:
        momentum = df["close"] - df["close"].shift(mom_window)
        df[f"momentum_{mom_window}"] = momentum / df["close"].shift(mom_window)
    print(f"[Features] Price Momentum Oscillator computed in {time.time() - start_time:.3f}s")

    print("[Features] All features computed successfully!")
    return df
