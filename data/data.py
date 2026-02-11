import yfinance as yf
import databento as db
import os
from datetime import datetime, timedelta
import pandas as pd
import dotenv
dotenv.load_dotenv()

DATABENTO_API_KEY = os.getenv("DATABENTO_API_KEY")
client = db.Historical(DATABENTO_API_KEY)
dataset = "GLBX.MDP3"

def get_data2():
    df = yf.download("ES=F", interval="5m", progress=False)
    df.columns = df.columns.get_level_values(0)
    df.dropna(inplace=True)
    return df

def get_data():
    today = datetime.now()
    # Request enough history: LOOKBACK_WINDOW (1000) + ~300 for rolling features
    start_date = today - timedelta(days=21)


    # Request OHLCV-1m data for the specific contract MESH6
    data = client.timeseries.get_range(
        dataset=dataset,
        schema="ohlcv-1m",
        symbols="MESH6",
        stype_in="raw_symbol",
        start=start_date.strftime("%Y-%m-%d"),
        end=today.strftime("%Y-%m-%dT%H:%M:%S"),
    )

    # Convert to DataFrame
    df = data.to_df()
    print(df)

    # Ensure DatetimeIndex (databento may use ts_event as index or column)
    if not isinstance(df.index, pd.DatetimeIndex):
        time_col = "ts_event" if "ts_event" in df.columns else df.index.name or df.columns[0]
        if time_col in df.columns:
            df = df.set_index(pd.to_datetime(df[time_col], unit="ns")).drop(columns=[time_col], errors="ignore")
        else:
            df.index = pd.to_datetime(df.index, unit="ns")

    # Convert to 5m candles (each 5m candle starts on minute % 5 == 0)
    ohlcv = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    cols = [c for c in ohlcv if c in df.columns]
    agg = {c: ohlcv[c] for c in cols}
    df_5m = df[cols].resample("5min").agg(agg).dropna(how="all")

    # Match yfinance format: column names and order [Close, High, Low, Open, Volume]
    out = pd.DataFrame(
        {
            "Close": df_5m["close"].astype(float),
            "High": df_5m["high"].astype(float),
            "Low": df_5m["low"].astype(float),
            "Open": df_5m["open"].astype(float),
            "Volume": df_5m["volume"].astype(int),
        },
        index=df_5m.index,
    )
    # yfinance-style: timezone-aware MultiIndex so "Price" and "Datetime" render on two lines (not "Price Datetime")
    if out.index.tz is None:
        out.index = out.index.tz_localize("UTC")
    out.index = pd.MultiIndex.from_arrays(
        [["ES=F"] * len(out), out.index],
        names=["Price", "Datetime"],
    )
    out.dropna(inplace=True)
    return out

# d1 = get_data2()
# d2 = get_data()
# print(d1.shape)
# print(d2.shape)
# print("Databento Data")
# print(d1.head(5))
# print()
# print("YFinance Data")
# print(d2.head(5))