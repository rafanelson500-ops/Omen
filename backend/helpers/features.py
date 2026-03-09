import numpy as np
import pandas as pd
import time
from scipy.stats import kurtosis
from helpers.vp import add_value_area_levels
from helpers.har_rv import add_har_rv
from helpers.hurst import rolling_hurst

def add_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    start_time = time.time()

    # calculate log returns
    log_ret = np.log(df["close"] / df["close"].shift(1))

    df['new_session'] = np.where(df['time'].diff() > 1800000, 1, 0)  # 30 minutes in milliseconds
    
    session_id = df["new_session"].cumsum()
    log_ret = np.where(df["new_session"] == 1, 0, log_ret)

    # calculate har_rv and volatility
    df = add_har_rv(df)
    df = add_value_area_levels(df)
    vol = np.sqrt(df["har_rv"]).clip(lower=1e-6)

    typical_price = (df["high"] + df["low"] + df["close"]) / 3
    tpv = typical_price * df["volume"]
    cum_tpv = tpv.groupby(session_id).cumsum()
    cum_vol = df["volume"].groupby(session_id).cumsum()

    df["session_vwap"] = cum_tpv / cum_vol

    # efficiency ratio
    er_lookbacks = [6,12,24]
    for er_lookback in er_lookbacks:
        net_move = (df["close"] - df["close"].shift(er_lookback)).abs()
        total_move = df["close"].diff().abs().rolling(er_lookback).sum()
        df["efficiency_ratio_"+str(er_lookback)] = net_move / (total_move + 1e-10)
    # rv_short_med_ratio
    rv_short_smooth = df["rv_short"].rolling(24, min_periods=1).mean()
    df["rv_short_med_ratio"] = np.log((rv_short_smooth + 1e-10) / (df["rv_medium"] + 1e-10))
    # mean_deviation
    raw_deviation = ((df["close"] - df["session_vwap"]) / vol).clip(-5, 5)
    df["mean_deviation"] = raw_deviation.ewm(span=12, adjust=False).mean()
    # vol_expansion
    df["vol_expansion"] = (rv_short_smooth / (df["rv_long"] + 1e-10)).clip(upper=1000)
    # hurst
    df["hurst"] = rolling_hurst(np.log(df["close"]), 100)

    log_ret = pd.Series(
        np.where(df["new_session"] == 1, 0, log_ret),
        index=df.index
    )

    # ── GBT features (target-aligned: EMA divergence / convergence) ──────────────
    # target = (|close[t+6] - ema[t+6]| - |close[t] - ema[t]|) / sqrt(har_rv)
    # Positive → price diverges further from EMA (momentum/trend continuation).
    # Negative → price reverts toward EMA (mean-reversion snap-back).
    # Features are designed to quantify: current EMA stretch, its rate of change,
    # return alignment with that stretch, vol regime, and session/range anchors.

    ema          = df["close"].ewm(span=20).mean()   # same EMA as target
    ema_dist_raw = df["close"] - ema                 # signed deviation, price units

    # 1. Signed EMA distance (vol-normalised) — direction + magnitude of stretch
    df["ema_dist"]     = (ema_dist_raw / vol).clip(-8, 8)

    # 2. Unsigned EMA distance — primary driver of mean-reversion pull;
    #    large |d| raises probability that target < 0
    df["ema_dist_abs"] = df["ema_dist"].abs()

    # 3. EMA divergence rate of change — are we currently stretching (+) or compressing (-)?
    df["ema_div_chg_3"] = df["ema_dist_abs"] - df["ema_dist_abs"].shift(3)
    df["ema_div_chg_6"] = df["ema_dist_abs"] - df["ema_dist_abs"].shift(6)

    # 4. Return–EMA alignment — positive = recent returns moving *away* from EMA
    #    (divergence momentum); negative = moving *toward* EMA (convergence pressure)
    df["ret_ema_align"] = (
        (np.sign(ema_dist_raw) * log_ret.rolling(3).sum()) / vol
    ).clip(-5, 5)

    # 5. EMA slope and curvature (same span and horizon h=6 as target EMA)
    #    A fast-moving EMA narrows the pull-back window; curvature signals inflections
    df["ema_slope"]     = ema.diff(3) / vol
    df["ema_slope_chg"] = ema.diff(3).diff(3) / vol

    # 6. EMA deviation z-score vs rolling history — how extreme is the current stretch
    #    relative to recent norms? (high z-score → heightened reversion probability)
    d_roll_mean = df["ema_dist_abs"].rolling(48, min_periods=10).mean()
    d_roll_std  = df["ema_dist_abs"].rolling(48, min_periods=10).std().clip(lower=1e-6)
    df["ema_dist_zscore"] = (df["ema_dist_abs"] - d_roll_mean) / d_roll_std

    # 7. Vol regime (log ratios — symmetric around 0; expanding vol sustains divergence)
    df["vol_ratio_fast"] = np.log((df["rv_short"]  + 1e-10) / (df["rv_medium"] + 1e-10))
    df["vol_ratio_slow"] = np.log((df["rv_medium"] + 1e-10) / (df["rv_long"]   + 1e-10))

    # 8. VWAP deviation — session-level anchor independent of EMA; captures intraday drift
    df["vwap_dist"] = (df["close"] - df["session_vwap"]) / vol

    # 9. Range position (centred around 0) — ±0.5 = near high/low; signals extreme stretch
    lookback = 20
    rng = (
        df["high"].rolling(lookback).max() - df["low"].rolling(lookback).min()
    ).clip(lower=1e-6)
    df["range_pos"] = (df["close"] - df["low"].rolling(lookback).min()) / rng - 0.5

    print(f"Features computed in {time.time() - start_time:.3f}s")

    return df

def add_target(df):
    h = 6
    ema = df["close"].ewm(span=20).mean()
    df["ema"] = ema
    df["target"] = (
        (abs(df["close"].shift(-h) - ema.shift(-h)) - abs(df["close"] - ema)) / np.sqrt(df["har_rv"])*1e-4
    ).clip(-5,5)
    return df