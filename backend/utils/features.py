import numpy as np
import pandas as pd

def featurize(df):
    df["ts_event"] = pd.to_datetime(df["ts_event"], utc=True)

    ny = df["ts_event"].dt.tz_convert("America/New_York")
    m = ny.dt.hour * 60 + ny.dt.minute
    df["session"] = np.select(
        [
            (m >= 1020) & (m < 1140),
            (m >= 1140) | (m < 8 * 60 + 30),
            (m >= 8 * 60 + 30) & (m < 9 * 60 + 30),
            (m >= 9 * 60 + 30) & (m < 11 * 60),
            (m >= 11 * 60) & (m < 15 * 60),
            (m >= 15 * 60) & (m < 16 * 60),
            (m >= 16 * 60) & (m < 17 * 60),
        ],
        [
            "post_close",
            "overnight",
            "pre-open",
            "open",
            "lunch",
            "power hour",
            "pre-close",
        ],
        default="unknown",
    )
    
    df = es_features(df)
    df = cl_features(df)

    # Rolling Pearson correlation of ES vs CL returns over corr_window bars
    df["cross_asset_corr"] = df["es_returns"].rolling(20).corr(df["cl_returns"])

    return df


def es_features(df):
    df["es_returns"] = np.where(df['ts_event'] - df['ts_event'].shift(1) == pd.Timedelta(minutes=5), np.log(df["es_close"]).diff(), 0)

    # HMM Features
    df["es_rvol"] = df["es_returns"].rolling(12).std()
    df["es_efficiency"] = (
        df["es_close"].diff(12).abs()
        / df["es_returns"].abs().rolling(12).sum()
    )
    df["es_vol_ratio"] = (
        df["es_returns"].rolling(6).std()
        / df["es_returns"].rolling(24).std()
    )
    df["es_rel_volume"] = df["es_volume"] / df["es_volume"].rolling(24).mean()

    return df
def cl_features(df):
    df["cl_returns"] = np.where(df['ts_event'] - df['ts_event'].shift(1) == pd.Timedelta(minutes=5), np.log(df["cl_close"]).diff(), 0)

    # HMM Features
    df["cl_rvol"] = df["cl_returns"].rolling(18).std()
    df["cl_efficiency"] = (
        df["cl_close"].diff(12).abs()
        / df["cl_returns"].abs().rolling(18).sum()
    )
    df["cl_vol_ratio"] = (
        df["cl_returns"].rolling(12).std()
        / df["cl_returns"].rolling(28).std()
    )
    df["cl_rel_volume"] = df["cl_volume"] / df["cl_volume"].rolling(28).mean()
    return df
