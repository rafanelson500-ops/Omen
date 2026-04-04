import numpy as np

from classes.regime import vwap_and_std_from_sums

TPS_WINDOW = 30
AGGRESSION_EFFICIENCY_WINDOW = 30
ORDERFLOW_WINDOW = 10
VWAP_WINDOW = 30

# Live emit: latest row has real rolling values (not shift/rolling warmup).
LIVE_TICK_WARMUP = 1#AGGRESSION_EFFICIENCY_WINDOW * 2  # shift(30) + rolling(30) on aggression_efficiency
LIVE_MEDIUM_WARMUP = 1#ORDERFLOW_WINDOW
LIVE_LONG_WARMUP = 1#VWAP_WINDOW


def add_tick_features(df):
    TPS_SPIKE_MLT = 5
    TPS_STALL_MLT = 5

    # TPS
    tps = TPS_WINDOW / (df['time'] - df['time'].shift(TPS_WINDOW)).fillna(0.1)
    df['tps_delta'] = abs(tps - tps.shift(1))
    avg_tps_delta = df['tps_delta'].rolling(TPS_WINDOW).mean()
    time_delta = df['time'] - df['time'].shift(1)
    df['tps_spike'] = np.where(df['tps_delta'] > TPS_SPIKE_MLT * avg_tps_delta, 1, 0)
    df['tps_stall'] = np.where(time_delta > TPS_STALL_MLT / tps, 1, 0)

    # Aggression
    df['aggression_efficiency'] = (df['close'] - df['close'].shift(AGGRESSION_EFFICIENCY_WINDOW)) / tps
    df['agg_eff_max'] = df['aggression_efficiency'].rolling(AGGRESSION_EFFICIENCY_WINDOW).max()
    df['agg_eff_min'] = df['aggression_efficiency'].rolling(AGGRESSION_EFFICIENCY_WINDOW).min()
    df['agg_eff_spike'] = np.where(df['aggression_efficiency'] >= df['agg_eff_max'], 1, np.where(df['aggression_efficiency'] <= df['agg_eff_min'], -1, 0))

    return df.fillna(0.1)

def microstate_features(df):
    df["avg_delta"] = df["delta"].rolling(ORDERFLOW_WINDOW).mean()
    df["raw_delta"] = df["delta"]

    return df.fillna(0.1)

def add_context_features(df):
    VWAP_SIGMAS = [1, 2]

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