def normalize_HMM_features(df):
    df['Returns'] = (df['Returns'] - df['Returns'].mean()) / df['Returns'].std()
    df['RealizedVolatility'] = (df['RealizedVolatility'] - df['RealizedVolatility'].mean()) / df['RealizedVolatility'].std()
    df['Autocorrelation'] = (df['Autocorrelation'] - df['Autocorrelation'].mean()) / df['Autocorrelation'].std()
    return df