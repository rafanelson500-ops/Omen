import os
from collections import deque
import databento as db
import dotenv
import pandas as pd
import time
import threading
from datetime import datetime

dotenv.load_dotenv()

DATABENTO_API_KEY = os.getenv("DATABENTO_API_KEY")
dataset = "GLBX.MDP3"
symbol = "NQM6"

class DatastreamEngine:
    def __init__(self):
        print("Initializing Datastream Engine")
        self.client = db.Live(DATABENTO_API_KEY)
        self.callbacks = []
    
    def start(self):
        self.client.subscribe(
            dataset=dataset,
            schema="trades",
            symbols=symbol,
            stype_in="raw_symbol",
        )
        self.client.subscribe(
            dataset=dataset,
            schema="mbp-10",
            symbols=symbol,
            stype_in="raw_symbol",
        )
        self.client.add_callback(self._on_tick)
        self.client.start()

    def start_simulated(self):
        def sim():
            ticks = pd.read_csv("trades.csv")
            ticks["ts_event"] = pd.to_datetime(ticks["ts_event"], utc=True)

            class Tick:
                def __init__(self, price, side, size, ts):
                    self.pretty_price = price
                    self.side = side
                    self.size = size
                    self.ts_event = ts

            for index in range(len(ticks) - 1):
                row = ticks.iloc[index]
                now = row["ts_event"]
                next_ts = ticks.iloc[index + 1]["ts_event"]

                self._on_tick(
                    Tick(row["price"], row["side"], row["size"], int(now.value))
                )
                time.sleep(max(0.0, (next_ts - now).total_seconds()))

        thread = threading.Thread(target=sim)
        thread.start()

    def subscribe(self, callback):
        self.callbacks.append(callback)

    def _on_tick(self, tick):
        try:
            price = float(tick.pretty_price)
            side = int(-1 if tick.side == "A" else 1)
            size = int(tick.size)
            ts = float(tick.ts_event / 1_000_000_000)

            clean_tick = {
                "price": price,
                "side": side,
                "size": size,
                "ts": ts
            }

            for callback in self.callbacks:
                callback(clean_tick)
        except Exception as e:
            print(e)
            pass
