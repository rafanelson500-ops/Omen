import numpy as np
from helpers.volume_profile import add_value_area_levels
from helpers.config_handler import load_setting
import pandas as pd

return_window = 20
vol_window = 20
z_window = 300
lookback = 100

def add_regime_features(df):
    close_prev = df['close'].shift(1)
    ratio = np.where(
        (df['close'] > 0) & (close_prev > 0),
        df['close'] / close_prev,
        np.nan,
    )
    df['log_return'] = np.log(ratio)
    # time is Unix ms; gap > 300s => new session
    df['new_session'] = np.where(df['time'].diff() > 300, 1, 0)
    df['log_return'] = np.where(df['new_session'] == 1, 0, df['log_return'])

    # Use min_periods so we get values with partial windows (otherwise first 19 rows stay NaN)
    log_return_rolling = df['log_return'].rolling(return_window, min_periods=1)
    df['rolling_mean_return'] = log_return_rolling.mean()

    log_return_vol_rolling = df['log_return'].rolling(vol_window, min_periods=2)
    df['realized_vol'] = log_return_vol_rolling.std()

    df['vol_of_vol'] = df['realized_vol'].rolling(vol_window, min_periods=2).std()
    
    # Cache z_window rolling calculations (min_periods so short series get values)
    volume_z_rolling = df['volume'].rolling(z_window, min_periods=2)
    volume_z_mean = volume_z_rolling.mean()
    volume_z_std = volume_z_rolling.std()
    df['volume_z'] = np.where(volume_z_std > 0, (df['volume'] - volume_z_mean) / volume_z_std, 0)

    log_return_z_rolling = df['log_return'].rolling(z_window, min_periods=2)
    log_return_z_mean = log_return_z_rolling.mean()
    log_return_z_std = log_return_z_rolling.std()
    df['return_z'] = np.where(log_return_z_std > 0, (df['log_return'] - log_return_z_mean) / log_return_z_std, 0)
    return df

def add_technical_features(df):
    df = add_value_area_levels(df, lookback=lookback)

    # --- True Range ---
    prev_close = df['close'].shift(1)

    tr1 = df['high'] - df['low']
    tr2 = (df['high'] - prev_close).abs()
    tr3 = (df['low'] - prev_close).abs()

    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    # --- ATR (Wilder smoothing) ---
    df['atr'] = tr.ewm(alpha=1/14, adjust=False).mean()
    df['atr'] = np.where(df['atr'] > 0, df['atr'], 1e-6)

    # --- Session ID from NewSession flag ---
    # Assumes NewSession == 1 on first bar of each session
    df['session_id'] = df['new_session'].cumsum()

    # --- Typical Price ---
    typical_price = (df['high'] + df['low'] + df['close']) / 3

    # --- Session-based cumulative sums ---
    df['cum_vol'] = df.groupby('session_id')['volume'].cumsum()
    df['cum_tp_vol'] = (
        typical_price * df['volume']
    ).groupby(df['session_id']).cumsum()

    # --- Session VWAP ---
    df['vwap'] = df['cum_tp_vol'] / df['cum_vol']
    df['dir'] = np.sign(df['close'] - df['open'])

    return df

def add_prediction_features_chop(df):
    df['dist_to_val'] = (df['close'] - df['val']) / df['atr']
    df['dist_to_vah'] = (df['close'] - df['vah']) / df['atr']
    df['dist_to_vwap'] = (df['close'] - df['vwap']) / df['atr']
    df['upper_wick'] = df['high'] - df[['open','close']].max(axis=1)
    df['lower_wick'] = df[['open','close']].min(axis=1) - df['low']
    df['wick_ratio'] = (df['upper_wick'] - df['lower_wick']) / (df['high'] - df['low'] + 1e-6)
    df['persistence_5'] = df['dir'].rolling(5).sum() / 5
    df['stretch_3'] = (df['close'] - df['close'].shift(3)) / df['atr']
    return df

def add_prediction_features_trend(df):
    df['mom_12_atr'] = (df['close'] - df['close'].shift(12)) / df['atr']
    df['mom_4_atr'] = (df['close'] - df['close'].shift(4)) / df['atr']
    df['mom_1_atr'] = (df['close'] - df['close'].shift(1)) / df['atr']
    rolling_high = df['high'].rolling(16).max().shift(1)
    rolling_low = df['low'].rolling(16).min().shift(1)

    df['pullback_up'] = (rolling_high - df['close']) / df['atr']
    df['pullback_down'] = (df['close'] - rolling_low) / df['atr']
    df['ema_21'] = df['close'].ewm(span=21, adjust=False).mean()
    df['ema_slope'] = (df['ema_21'] - df['ema_21'].shift(5)) / df['atr']
    df['atr_expansion'] = df['atr'] / df['atr'].rolling(20).mean()
    df['trend_persistence_10'] = df['dir'].rolling(10).sum() / 10
    df['ema_alignment'] = (df['close'] - df['ema_21']) / df['atr']

    return df

def add_targets(df):
    target = load_setting("target")
    df['forward_return'] = np.log(df['close'].shift(-target) / df['close'])
    df['target'] = np.where(df['forward_return'] > 0, 1, -1)
    return df