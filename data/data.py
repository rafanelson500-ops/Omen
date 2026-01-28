import yfinance as yf
from config.config import SYMBOL, TIMEFRAME

def get_data():
    df = yf.download(SYMBOL, interval=TIMEFRAME)
    df.columns = df.columns.get_level_values(0)
    df.dropna(inplace=True)
    print(df.iloc[-1])
    return df
