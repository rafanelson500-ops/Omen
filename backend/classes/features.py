import numpy as np

from classes.regime import vwap_and_std_from_sums


def add_tick_features(df):
    TPS_WINDOW = 30
    AGGRESSION_EFFICIENCY_WINDOW = 30
    AGGRESSION_EFFICIENCY_K = 2

    # TPS
    tps = TPS_WINDOW / (df['time'] - df['time'].shift(TPS_WINDOW)).fillna(0.1)
    df['tps_delta'] = abs(tps - tps.shift(1))
    avg_tps_delta = df['tps_delta'].rolling(TPS_WINDOW).mean()
    df['tps_spike'] = np.where(df['tps_delta'] > 5 * avg_tps_delta, 1, 0)

    # Aggression
    df['aggression_efficiency'] = (df['close'] - df['close'].shift(AGGRESSION_EFFICIENCY_WINDOW)) / tps
    agg_eff_mean = df['aggression_efficiency'].rolling(AGGRESSION_EFFICIENCY_WINDOW).mean()
    agg_eff_std = df['aggression_efficiency'].rolling(AGGRESSION_EFFICIENCY_WINDOW).std()
    df['agg_eff_upper'] = agg_eff_mean + AGGRESSION_EFFICIENCY_K * agg_eff_std
    df['agg_eff_lower'] = agg_eff_mean - AGGRESSION_EFFICIENCY_K * agg_eff_std
    df['agg_eff_spike'] = np.where(df['aggression_efficiency'] > df['agg_eff_upper'], 1, np.where(df['aggression_efficiency'] < df['agg_eff_lower'], -1, 0))

    df['reprice_short'] = np.where(
        (df['agg_eff_spike'].shift(1) == 1) & (df['agg_eff_spike'] == 0), 1, 0
    )
    df['reprice_long'] = np.where(
        (df['agg_eff_spike'].shift(1) == -1) & (df['agg_eff_spike'] == 0), 1, 0
    )
    
    return df.fillna(0.1)

def microstate_features(df):
    ORDERFLOW_WINDOW = 10

    df["avg_delta"] = df["delta"].rolling(ORDERFLOW_WINDOW).mean()
    df["raw_delta"] = df["delta"]

    return df.fillna(0.1)

def add_context_features(df):
    VWAP_WINDOW = 30
    VWAP_SIGMAS = [1,2]

    # Volume-weighted VWAP + std around it (same as regime.vwap_and_std_around on bar closes/volumes).
    v = df["volume"].astype(float)
    p = df["close"].astype(float)
    sum_v = v.rolling(VWAP_WINDOW).sum()
    sum_pv = (p * v).rolling(VWAP_WINDOW).sum()
    sum_pv2 = (v * p * p).rolling(VWAP_WINDOW).sum()
    vw, std = vwap_and_std_from_sums(sum_v, sum_pv, sum_pv2)
    df["vwap"] = vw
    df["vwap_std"] = std

    for i in VWAP_SIGMAS:
        df[f'vwap_sigma_{i}'] = df['vwap'] + i * df['vwap_std']
        df[f'vwap_sigma_{-i}'] = df['vwap'] - i * df['vwap_std']

    return df.fillna(0.1)