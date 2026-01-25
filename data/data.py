import yfinance as yf
from config import SYMBOL, TIMEFRAME

def get_data():
    df = yf.download(SYMBOL, period="1d", interval=TIMEFRAME)
    df.columns = df.columns.get_level_values(0)
    df.dropna(inplace=True)
    return df
