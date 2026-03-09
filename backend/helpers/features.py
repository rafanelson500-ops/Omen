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
    df["ret_1"] = log_ret
    df["ret_3"] = log_ret.rolling(3).sum()
    df["ret_6"] = log_ret.rolling(6).sum()

    df["ema_dist"] = (df["close"] - df["close"].ewm(span=20).mean()) / vol

    df["vol_ratio_fast"] = df["rv_short"] / df["rv_medium"]
    df["vol_ratio_slow"] = df["rv_medium"] / df["rv_long"]

    lookback = 20

    df["range_pos"] = (
        (df["close"] - df["low"].rolling(lookback).min())
        / (df["high"].rolling(lookback).max() - df["low"].rolling(lookback).min())
    )

    df["vwap_dist"] = (df["close"] - df["session_vwap"]) / vol

    df["vwap_slope"] = df["session_vwap"].diff(5) / vol

    print(f"Features computed in {time.time() - start_time:.3f}s")

    return df

def add_target(df):
    h = 8
    df["target"] = (
        (df["close"].shift(-h) - df["close"])
        / np.sqrt(df["har_rv"]) * 1e-5
    ).clip(-1,1)
    return df