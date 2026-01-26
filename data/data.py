import yfinance as yf
from config import SYMBOL, TIMEFRAME, D

def get_data(training):
    if training:
        df = yf.download(SYMBOL, start=f"2026-01-{D}", end=f"2026-01-{D+1}", interval=TIMEFRAME).iloc[0:90]
    else:
        df = yf.download(SYMBOL, start=f"2026-01-{D}", end=f"2026-01-{D+1}", interval=TIMEFRAME)
    df.columns = df.columns.get_level_values(0)
    df.dropna(inplace=True)
    return df
