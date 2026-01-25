from helpers.volume_profile import add_value_area_levels

def featurize_HMM(df):
    df['Returns'] = df['Close'].pct_change()
    df['RealizedVolatility'] = df['Returns'].rolling(window=20).std()
    df['Autocorrelation'] = df['Returns'].rolling(window=20).apply(lambda x: x.autocorr(lag=1), raw=False)
    return df

def featurize_GBT(df):
    df['IsGreen'] = (df['Close'] >= df['Open']).astype(int)
    df['UpperWickLength'] = df['High'] - df[['Open', 'Close']].max(axis=1)
    df['LowerWickLength'] = df[['Open', 'Close']].min(axis=1) - df['Low']
    df['High(5)'] = df['High'].rolling(window=5).max()
    df['High(8)'] = df['High'].rolling(window=8).max()
    df['High(13)'] = df['High'].rolling(window=13).max()
    df['Low(5)'] = df['Low'].rolling(window=5).min()
    df['Low(8)'] = df['Low'].rolling(window=8).min()
    df['Low(13)'] = df['Low'].rolling(window=13).min()
    df = add_value_area_levels(df)
    return df