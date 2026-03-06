import numpy as np
import pandas as pd
import time
from scipy.stats import kurtosis
from helpers.vp import add_value_area_levels
from helpers.har_rv import add_har_rv


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
    vol = np.sqrt(df["har_rv"]).clip(lower=1e-6)
    
    #calculate session vwap\
    typical_price = (df["high"] + df["low"] + df["close"]) / 3

    df["session_vwap"] = (
        df.groupby(session_id)
        .apply(lambda g: (typical_price.loc[g.index] * df.loc[g.index, "volume"]).cumsum() / df.loc[g.index, "volume"].cumsum())
        .droplevel(0)
        .reindex(df.index)
    )
    
    # calculate ema
    df["ema"] = df["close"].ewm(span=12, adjust=False).mean()

    # calculate value area levels & poc
    df = add_value_area_levels(df)

    # calculate spreads
    ema_vwap_spread = abs(df["session_vwap"] - df["ema"])
    vwap_poc_spread = abs(df["session_vwap"] - df["poc"])
    poc_ema_spread = abs(df["poc"] - df["ema"])

    # calculate mean and std of spreads
    spreads = pd.concat([
        ema_vwap_spread,
        vwap_poc_spread,
        poc_ema_spread
    ], axis=1)

    df["vol_accel"] = (df["har_rv"] - df["har_rv"].shift(1)) / df["har_rv"].shift(1)
    df["mean_spread"] = spreads.mean(axis=1) / vol
    df["spread_std"]  = spreads.std(axis=1)  / vol
    df["mean_compression"] = spreads.max(axis=1) / vol

    # calculate mean divergence
    df["composite_mean"] = pd.concat([
        df["ema"],
        df["session_vwap"],
        df["poc"]
    ], axis=1).mean(axis=1)

    df["mean_divergence"] = (df["close"] - df["composite_mean"]) / vol
    df["mean_velocity"] = (df["close"].diff()) / vol
    df["divergence_change"] = df["mean_divergence"].diff()
    df["har_sigma"] = np.sqrt(df["har_rv"] * 1e8).rolling(3).mean()

    df["dist_vah"] = (df["close"] - df["vah"]) / vol
    df["dist_val"] = (df["close"] - df["val"]) / vol

    print(f"Features computed in {time.time() - start_time:.3f}s")

    return df

def add_target(df):

    dist_now = abs(df["close"] - df["composite_mean"])

    future_distances = []
    for i in range(1, 6):
        future_distances.append(
            abs(df["close"].shift(-i) - df["composite_mean"])
        )

    future_dist = pd.concat(future_distances, axis=1)

    dist_reduction = dist_now.to_numpy()[:, None] - future_dist.to_numpy()

    # weight earlier bars more
    weights = np.array([5,4,3,2,1])

    path_score = (dist_reduction * weights).sum(axis=1) / weights.sum()

    reversion_strength = path_score / df["har_sigma"]

    df["target"] = (reversion_strength > 0.5).astype(int)

    return df