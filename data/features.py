from helpers.volume_profile import add_value_area_levels
from config.config import LOOKBACK_WINDOW, TARGET
import numpy as np

return_window = 20
vol_window = 20
z_window = 300

def add_features(df):
# Regieme HMM Model Inputs
    df['LogReturn'] = np.log(df['Close'] / df['Close'].shift(1))
    
    # Cache rolling calculations to avoid recomputing
    log_return_rolling = df['LogReturn'].rolling(return_window)
    df['RollingMeanReturn'] = log_return_rolling.mean()
    
    log_return_vol_rolling = df['LogReturn'].rolling(vol_window)
    df['RealizedVol'] = log_return_vol_rolling.std()
    
    df['VolOfVol'] = df['RealizedVol'].rolling(vol_window).std()
    
    # Cache z_window rolling calculations
    volume_z_rolling = df['Volume'].rolling(z_window)
    volume_z_mean = volume_z_rolling.mean()
    volume_z_std = volume_z_rolling.std()
    df['VolumeZ'] = (df['Volume'] - volume_z_mean) / volume_z_std
    
    log_return_z_rolling = df['LogReturn'].rolling(z_window)
    log_return_z_mean = log_return_z_rolling.mean()
    log_return_z_std = log_return_z_rolling.std()
    df['ReturnZ'] = (df['LogReturn'] - log_return_z_mean) / log_return_z_std

# Gradient Boosted Tree Model Inputs
     # 1️⃣ 12-bar Momentum
    df['Momentum_12'] = np.log(
        df['Close'] / df['Close'].shift(12)
    )

    # 2️⃣ Distance from 20-period moving average
    ma_20 = df['Close'].rolling(20).mean()
    df['DistFromMA20'] = (df['Close'] - ma_20) / ma_20

    # 3️⃣ Range Position (where we are in 20-bar range)
    rolling_high_20 = df['High'].rolling(20).max()
    rolling_low_20 = df['Low'].rolling(20).min()

    df['RangePosition'] = (
        (df['Close'] - rolling_low_20) /
        (rolling_high_20 - rolling_low_20)
    )

    # 4️⃣ ATR and Volatility Compression (ATR Z-score)
    df['ATR'] = (
        (df['High'] - df['Low'])
        .rolling(14)
        .mean()
    )

    atr_roll = df['ATR'].rolling(200)
    df['ATR_Z'] = (
        df['ATR'] - atr_roll.mean()
    ) / atr_roll.std()

    # 5️⃣ Breakout Detection (shifted to prevent leakage)
    df['BreakoutHigh20'] = (
        df['Close'] >
        df['High'].rolling(20).max().shift(1)
    ).astype(int)

    df['BreakoutLow20'] = (
        df['Close'] <
        df['Low'].rolling(20).min().shift(1)
    ).astype(int)
    
    lookback = min(LOOKBACK_WINDOW, max(10, len(df) // 3))  # Use 1/3 of data to leave more rows
    df = add_value_area_levels(df, lookback=lookback)
    df['VALTap'] = np.where((df['Close'] > df['VAL']) & (df['Low'] < df['VAL']), 1, 0)
    df['VAHTap'] = np.where((df['Close'] < df['VAH']) & (df['High'] > df['VAH']), 1, 0)

# Target for Gradient Boosted Tree Model
    df['ForwardReturn'] = np.log(df['Close'].shift(-TARGET) / df['Close'])
    return df