from helpers.volume_profile import add_value_area_levels
import numpy as np

def featurize_HMM(df):
    df['Returns'] = df['Close'].pct_change()
    df['RealizedVolatility'] = df['Returns'].rolling(window=10).std()
    df['Autocorrelation'] = df['Returns'].rolling(window=10).apply(lambda x: x.autocorr(lag=1), raw=False)
    return df

def featurize_GBT(df):
    # Add Forward Return target - predicts next candle's return percentage
    # For each row i, ForwardReturn[i] = (Close[i+1] - Close[i]) / Close[i]
    # This is the return we want to predict at time i
    df['ForwardReturn'] = (df['Close'].shift(-1) - df['Close']) / df['Close']
    
    # Keep IsGreen for backward compatibility if needed
    df['IsGreen'] = (df['Close'] >= df['Open']).astype(int)
    df['UpperWickLength'] = df['High'] - df[['Open', 'Close']].max(axis=1)
    df['LowerWickLength'] = df[['Open', 'Close']].min(axis=1) - df['Low']
    df['High(3)'] = df['High'].rolling(window=3).max()
    df['High(5)'] = df['High'].rolling(window=5).max()
    df['High(8)'] = df['High'].rolling(window=8).max()
    df['Low(3)'] = df['Low'].rolling(window=3).min()
    df['Low(5)'] = df['Low'].rolling(window=5).min()
    df['Low(8)'] = df['Low'].rolling(window=8).min()
    # Use adaptive lookback: min of 100 or available data size (leave buffer for other features)
    # HMM uses window=10, so we want to ensure we have data left after both
    lookback = min(100, max(10, len(df) // 3))  # Use 1/3 of data to leave more rows
    df = add_value_area_levels(df, lookback=lookback)
    df['VALTap'] = np.where((df['Close'] > df['VAL']) & (df['Low'] < df['VAL']), 1, 0)
    df['VAHTap'] = np.where((df['Close'] < df['VAH']) & (df['High'] > df['VAH']), 1, 0)
    return df