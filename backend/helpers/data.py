from typing import Literal
import requests
from dotenv import load_dotenv
import os
import redis
import json
import time
import pandas as pd
from datetime import datetime, timezone
from helpers.vp import add_value_area_levels

load_dotenv()

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
redis_client = redis.from_url(REDIS_URL)

OHLCV_LIST_KEY = "ohlcv:ES:list"

def get_data():
    def _parse_ts(ts_str):
        """Parse timestamp string to Unix seconds for ordering."""
        if not ts_str:
            return 0
        try:
            s = str(ts_str).replace("Z", "+00:00").strip()
            return datetime.fromisoformat(s).timestamp()
        except Exception:
            return 0
    attemps = 10
    df = None
    while attemps > 0:
        try:
            print("Attempting to get data from Redis")
            raw = redis_client.get(OHLCV_LIST_KEY)
            print("Got data from Redis")
            candles = json.loads(raw) if raw else []
            print("Parsed data")
            candles = sorted(candles, key=lambda c: _parse_ts(c.get("timestamp")))
            df = pd.DataFrame(candles)
            df["timestamp"] = pd.to_datetime(df["timestamp"], format="mixed")
            df = df.set_index("timestamp")
            attemps = 0
        except Exception as e:
            print("Error getting data from Redis: ", e)
            raise e
            attemps -= 1
            time.sleep(0.1)

    # Resample to 5m (bins start when minute % 5 == 0: 10:00, 10:05, 10:10, ...)
    completed = df.resample("5min").agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
    ).dropna(how="all")
    # One row per 5m bin: index is bin start time; drop duplicate index rows so each candle has unique time
    completed = completed[~completed.index.duplicated(keep="first")]

    # Include the currently-forming 5m candle (raw ticks after the last completed bin)
    if not completed.empty:
        forming_start = completed.index[-1] + pd.Timedelta(minutes=5)
        forming_ticks = df[df.index >= forming_start]
        if not forming_ticks.empty:
            partial = pd.DataFrame([{
                "open":   forming_ticks["open"].iloc[0],
                "high":   forming_ticks["high"].max(),
                "low":    forming_ticks["low"].min(),
                "close":  forming_ticks["close"].iloc[-1],
                "volume": forming_ticks["volume"].sum(),
            }], index=[forming_start])
            completed = pd.concat([completed, partial])

    completed["time"] = (completed.index.astype("int64") // 10**6).astype("int64")  # nanoseconds -> milliseconds
    cols = ["time", "open", "high", "low", "close", "volume"]
    df = completed[cols].dropna()
    return df