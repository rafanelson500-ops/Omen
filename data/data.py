import yfinance as yf
import databento as db
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import pandas as pd
import dotenv
import json
import redis
dotenv.load_dotenv()
from config.config import LOOKBACK_WINDOW

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


def get_data():
    raw = redis_client.get(OHLCV_LIST_KEY)
    candles = json.loads(raw) if raw else []
    candles = sorted(candles, key=lambda c: _parse_ts(c.get("timestamp")))
    df = pd.DataFrame(candles)
    df["timestamp"] = pd.to_datetime(df["timestamp"], format="mixed")
    df = df.set_index("timestamp")
    # Resample to 5m (bins start when minute % 5 == 0: 10:00, 10:05, 10:10, ...)
    df = df.resample("5min").agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
    ).dropna(how="all")
    return df.iloc[-int(LOOKBACK_WINDOW*1.5):]
