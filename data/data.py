import yfinance as yf
from config.config import SYMBOL, TIMEFRAME

def get_data():
    df = yf.download("ES=F", interval=TIMEFRAME, progress=False)
    df.columns = df.columns.get_level_values(0)
    df.dropna(inplace=True)
    return df
