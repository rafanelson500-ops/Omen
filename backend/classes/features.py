def add_tick_features(df):
    TPS_WINDOW = 30

    df['tps'] = TPS_WINDOW / (df['time'] - df['time'].shift(TPS_WINDOW)).fillna(0)
    df['average_tps'] = df['tps'].rolling(TPS_WINDOW).mean()
    
    return df