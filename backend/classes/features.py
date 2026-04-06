import numpy as np
from classes.regime import vwap_and_std_from_sums
import joblib

TPS_WINDOW = 30
AGGRESSION_EFFICIENCY_WINDOW = 30
ORDERFLOW_WINDOW = 10
# Min completed long (100-tick) bars before live master slice; not used for VWAP math.
LIVE_LONG_MIN_BARS = 30

# Live emit: latest row has real rolling values (not shift/rolling warmup).
LIVE_TICK_WARMUP = 1#AGGRESSION_EFFICIENCY_WINDOW * 2  # shift(30) + rolling(30) on aggression_efficiency
LIVE_MEDIUM_WARMUP = 1#ORDERFLOW_WINDOW
LIVE_LONG_WARMUP = 1#LIVE_LONG_MIN_BARS

hmm_features = ["efficiency_ratio", "vol_ratio", "autocorr_1", "vwap_z"]


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

    return df.fillna(0)

def microstate_features(df):
    df["avg_delta"] = df["delta"].rolling(ORDERFLOW_WINDOW).mean()
    df["raw_delta"] = df["delta"]

    return df.fillna(0)

import numpy as np

def add_context_features(df):
    VWAP_SIGMAS = [1, 2]

    v = df["volume"].astype(float)
    p = df["close"].astype(float)

    # --- Session / cumulative VWAP + std (entire ``df`` from first row to each bar) ---
    sum_v = v.expanding().sum()
    sum_pv = (p * v).expanding().sum()
    sum_pv2 = (v * p * p).expanding().sum()
    vw, std = vwap_and_std_from_sums(sum_v, sum_pv, sum_pv2)

    df["vwap"] = vw
    df["vwap_std"] = std

    for i in VWAP_SIGMAS:
        df[f'vwap_sigma_{i}'] = df['vwap'] + i * df['vwap_std']
        df[f'vwap_sigma_{-i}'] = df['vwap'] - i * df['vwap_std']

    # =========================================================
    # ✅ NEW FEATURES FOR HMM
    # =========================================================

    # 1. Efficiency Ratio (trend vs chop)
    n = 20
    price_change = np.abs(p - p.shift(n))
    path_length = p.diff().abs().rolling(n).sum()
    df["efficiency_ratio"] = price_change / (path_length + 1e-9)

    # 2. Volatility Regime (expansion vs compression)
    returns = np.log(p).diff()
    short_vol = returns.rolling(10).std()
    long_vol = returns.rolling(50).std()
    df["vol_ratio"] = short_vol / (long_vol + 1e-9)

    # 3. Autocorrelation (mean reversion vs trend)
    df["autocorr_1"] = returns.rolling(30).apply(
        lambda x: np.corrcoef(x[:-1], x[1:])[0, 1] if len(x) > 1 else 0,
        raw=True
    )

    # 4. VWAP Z-Score (distance from equilibrium)
    df["vwap_z"] = (p - df["vwap"]) / (df["vwap_std"] + 1e-9)

    df = add_regime(df)

    return df

def add_regime(df):
    df = df.fillna(0.0)
    hmm_model = joblib.load("models/hmm.pkl")
    df["hmm_state"] = hmm_model.predict(df[hmm_features].values)

    return df