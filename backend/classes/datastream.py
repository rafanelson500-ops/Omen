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
symbol = "ES.v.0"

class Datastream:
    def __init__(self, emit_tick, emit_medium_tick, emit_long_tick) -> None:
        print("Initializing Datastream Engine")
        self.tick_counter = 0
        self.short_df = pd.DataFrame()
        self.medium_df = pd.DataFrame()
        self.long_df = pd.DataFrame()

        self.emit_tick = emit_tick
        self.emit_medium_tick = emit_medium_tick
        self.emit_long_tick = emit_long_tick

        self.medium_tick_build = {"time": 0, "open": 0, "high": 0, "low": 0, "close": 0, "delta": 0}
        self.long_tick_build = {"time": 0, "open": 0, "high": 0, "low": 0, "close": 0, "delta": 0}

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

        short_df["time"] = (short_df["ts_event"]).astype("int64") // 1_000
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

        self.short_df = short_df
        self.medium_df = medium_df
        self.long_df = long_df

        return short_df, medium_df, long_df
    
    def live(self):
        def on_tick(tick):
            price = tick.pretty_price
            ts_event = tick.ts_event
            size = tick.size
            side = tick.side
            self.tick_counter += 1
            self.short_df.append({
                "time": ts_event,
                "open": price,
                "high": price,
                "low": price,
                "close": price,
                "delta": size * side
            })
            self.emit_tick()

            if self.tick_counter % 10 == 0:
                self.medium_df.append(self.medium_tick_build)
                self.emit_medium_tick()
                self.medium_tick_build = {"time": ts_event, "open": price, "high": price, "low": price, "close": price, "delta": size * side}
            else:
                self.medium_tick_build["delta"] += size * side

            if self.tick_counter % 100 == 0:
                self.long_df.append(self.long_tick_build)
                self.emit_long_tick()
                self.long_tick_build = {"time": ts_event, "open": price, "high": price, "low": price, "close": price, "delta": size * side}
            else:
                self.long_tick_build["delta"] += size * side
                self.long_tick_build["high"] = max(self.long_tick_build["high"], price)
                self.long_tick_build["low"] = min(self.long_tick_build["low"], price)
                self.long_tick_build["close"] = price

        client = db.Live(DATABENTO_API_KEY)
        print("Getting live ticks")
        client.subscribe(
            dataset = dataset,
            symbols = symbol,
            stype_in = "continuous",
            schema = "trades"
        )
        client.add_callback(on_tick)
        client.start()

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