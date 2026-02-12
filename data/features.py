from helpers.volume_profile import add_value_area_levels
from config.config import LOOKBACK_WINDOW, TARGET
import numpy as np

return_window = 20
vol_window = 20
z_window = 300

def add_features(df):
# Regieme HMM Model Inputs
    # Safe log-return: avoid log(0) or log(negative); first row stays NaN from shift
    close_prev = df['close'].shift(1)
    ratio = np.where(
        (df['close'] > 0) & (close_prev > 0),
        df['close'] / close_prev,
        np.nan,
    )
    df['LogReturn'] = np.log(ratio)

    # Use min_periods so we get values with partial windows (otherwise first 19 rows stay NaN)
    log_return_rolling = df['LogReturn'].rolling(return_window, min_periods=1)
    df['RollingMeanReturn'] = log_return_rolling.mean()

    log_return_vol_rolling = df['LogReturn'].rolling(vol_window, min_periods=2)
    df['RealizedVol'] = log_return_vol_rolling.std()

    df['VolOfVol'] = df['RealizedVol'].rolling(vol_window, min_periods=2).std()
    
    # Cache z_window rolling calculations (min_periods so short series get values)
    volume_z_rolling = df['volume'].rolling(z_window, min_periods=2)
    volume_z_mean = volume_z_rolling.mean()
    volume_z_std = volume_z_rolling.std()
    df['VolumeZ'] = np.where(volume_z_std > 0, (df['volume'] - volume_z_mean) / volume_z_std, 0)

    log_return_z_rolling = df['LogReturn'].rolling(z_window, min_periods=2)
    log_return_z_mean = log_return_z_rolling.mean()
    log_return_z_std = log_return_z_rolling.std()
    df['ReturnZ'] = np.where(log_return_z_std > 0, (df['LogReturn'] - log_return_z_mean) / log_return_z_std, 0)

# Gradient Boosted Tree Model Inputs
     # 1️⃣ 12-bar Momentum
    df['Momentum_12'] = np.log(
        df['close'] / df['close'].shift(12)
    )

    # 2️⃣ Distance from 20-period moving average
    ma_20 = df['close'].rolling(20).mean()
    df['DistFromMA20'] = (df['close'] - ma_20) / ma_20

    # 3️⃣ Range Position (where we are in 20-bar range)
    rolling_high_20 = df['high'].rolling(20).max()
    rolling_low_20 = df['low'].rolling(20).min()

    df['RangePosition'] = (
        (df['close'] - rolling_low_20) /
        (rolling_high_20 - rolling_low_20)
    )

    # 4️⃣ ATR and Volatility Compression (ATR Z-score)
    df['ATR'] = (
        (df['high'] - df['low'])
        .rolling(14)
        .mean()
    )

    atr_roll = df['ATR'].rolling(200)
    df['ATR_Z'] = (
        df['ATR'] - atr_roll.mean()
    ) / atr_roll.std()

    # 5️⃣ Breakout Detection (shifted to prevent leakage)
    df['BreakoutHigh20'] = (
        df['close'] >
        df['high'].rolling(20).max().shift(1)
    ).astype(int)

    df['BreakoutLow20'] = (
        df['close'] <
        df['low'].rolling(20).min().shift(1)
    ).astype(int)
    
    lookback = min(LOOKBACK_WINDOW, max(10, len(df) // 3))  # Use 1/3 of data to leave more rows
    df = add_value_area_levels(df, lookback=lookback)
    df['VALTap'] = np.where((df['close'] > df['VAL']) & (df['low'] < df['VAL']), 1, 0)
    df['VAHTap'] = np.where((df['close'] < df['VAH']) & (df['high'] > df['VAH']), 1, 0)

# Target for Gradient Boosted Tree Model
    df['ForwardReturn'] = np.log(df['close'].shift(-TARGET) / df['close'])
    return df