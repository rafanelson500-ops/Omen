from __future__ import annotations

import os
import time
from collections.abc import Callable
from typing import Any
import databento as db
import pandas as pd
import dotenv
import threading
import numpy as np
dotenv.load_dotenv()

DATABENTO_API_KEY = os.getenv("DATABENTO_API_KEY")
dataset = "GLBX.MDP3"
symbol = "NQ.v.0"

class Datastream:
    def __init__(self) -> None:
        print("Initializing Datastream Engine")

    def historical(self, start_date, end_date):
        client = db.Historical(DATABENTO_API_KEY)
        print(f"Getting ticks from {start_date} to {end_date}")
        ticks = client.timeseries.get_range(
            dataset = dataset,
            symbols = symbol,
            stype_in = "continuous",
            start = start_date,
            end = end_date,
            schema = "trades"   
        )
        short_df = ticks.to_df()[["ts_event", "size", "price", "side"]].dropna()
        short_df.index = np.arange(1, len(short_df) + 1)
        short_df["side"] = np.where(short_df["side"] == "B", 1, -1)

        short_df["time"] = short_df["ts_event"].astype(int)
        short_df["open"] = short_df["price"]
        short_df["high"] = short_df["price"]
        short_df["low"] = short_df["price"]
        short_df["close"] = short_df["price"]
        short_df["delta"] = short_df["size"] * short_df["side"]

        short_df.drop(columns=["price", "ts_event", "size", "side"], inplace=True)

        # Exact duplicate ts_event rows only. Does not fix JSON/JS: nanosecond ints
        # exceed Number.MAX_SAFE_INTEGER; see main.py before socket emit.
        short_df = short_df.drop_duplicates(subset=["time"], keep="last")

        medium_df = aggregate_ticks(short_df, 10)
        long_df = aggregate_ticks(short_df, 100)

        return short_df, medium_df, long_df

def aggregate_ticks(df, n):
    df = df.copy()
    return df.groupby(df.index // n).agg({
        "time": "first",
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "delta": "sum"
    })