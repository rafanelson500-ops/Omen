import dotenv
import os
import redis
import json
import pandas as pd
from datetime import datetime
from helpers.timing import crop_data

dotenv.load_dotenv()

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
redis_client = redis.from_url(REDIS_URL)

OHLCV_LIST_KEY = "ohlcv:ES:list"

def _parse_ts(ts_str):
    """Parse timestamp string to Unix seconds for ordering."""
    if not ts_str:
        return 0
    try:
        s = str(ts_str).replace("Z", "+00:00").strip()
        return datetime.fromisoformat(s).timestamp()
    except Exception:
        return 0

def get_data(data = "ALL", jsonify = True, include_volume = False):
    session = data
    print(f"Getting {session} data...")
    raw = redis_client.get(OHLCV_LIST_KEY)
    candles = json.loads(raw) if raw else []
    candles = sorted(candles, key=lambda c: _parse_ts(c.get("timestamp")))
    df = pd.DataFrame(candles)
    df["timestamp"] = pd.to_datetime(df["timestamp"], format="mixed")
    df = df.set_index("timestamp")
    #Resample to 5m (bins start when minute % 5 == 0: 10:00, 10:05, 10:10, ...)
    df = df.resample("5min").agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
    ).dropna(how="all")
    df = crop_data(df, session)
    # One row per 5m bin: index is bin start time; drop duplicate index rows so each candle has unique time
    df = df[~df.index.duplicated(keep="first")]
    df["time"] = (df.index.astype("int64") // 10**6).astype("int64")  # nanoseconds -> milliseconds
    cols = ["time", "open", "high", "low", "close"] if not include_volume else ["time", "open", "high", "low", "close", "volume"]
    if jsonify:
        return df[cols].dropna().iloc[-1500:].to_json(orient="records")
    else:
        return df[cols].dropna().iloc[-1500:]