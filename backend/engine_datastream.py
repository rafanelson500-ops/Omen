from __future__ import annotations

import os
import time
from typing import Any
import databento as db
import pandas as pd
import dotenv
import threading

dotenv.load_dotenv()

DATABENTO_API_KEY = os.getenv("DATABENTO_API_KEY")
dataset = "GLBX.MDP3"
symbol = "NQM6"

class DatastreamEngine:
    def __init__(self) -> None:
        print("Initializing Datastream Engine")
        self.callbacks = {}
        self.candle_states = {}
        self.candle_counter = 0

    def subscribe(self, n_ticks, cb_func) -> None:
        self.callbacks[n_ticks] = cb_func

    def start(self, simulated = False, speed = 1) -> None:
        if simulated:
            def sim():
                trades = pd.read_csv("trades.csv")
                trades["ts_event"] = pd.to_datetime(trades["ts_event"], utc=True)
                class Tick:
                    def __init__(self, price: Any, side: str, size: Any, ts_event: int) -> None:
                        self.pretty_price = price
                        self.side = side
                        self.size = size
                        self.ts_event = ts_event
                for i in range(len(trades)):
                    ts_ns = int(trades.iloc[i]["ts_event"].value)
                    tick = Tick(trades.iloc[i]["price"], trades.iloc[i]["side"], trades.iloc[i]["size"], ts_ns)
                    self._on_tick(tick)
                    if i + 1 < len(trades):
                        delay_s = (trades.iloc[i + 1]["ts_event"] - trades.iloc[i]["ts_event"]).total_seconds()
                        time.sleep(max(0.0, delay_s) / speed)
            self.thread = threading.Thread(target=sim)
            self.thread.daemon = True
            self.thread.start()
        else:
            self.client = db.Live(DATABENTO_API_KEY)
            self.client.subscribe(
                dataset=dataset,
                schema="trades",
                symbols=symbol,
                stype_in="raw_symbol",
            )
            self.client.add_callback(self._on_tick)
            self.client.start()

    def _on_tick(self, tick: Any) -> None:
        try:
            price = float(tick.pretty_price)
            ts = float(tick.ts_event / 1_000_000_000)

            self.candle_counter += 1
            for n in self.callbacks.keys():
                if n not in self.candle_states or "reset" in self.candle_states[n]: # initialize candle state for new n_ticks
                    self.candle_states[n] = {
                        "time": ts,
                        "open": price,
                        "high": price,
                        "low": price,
                        "close": price,
                    }
                else:
                    self.candle_states[n]["high"] = max(self.candle_states[n]["high"], price)
                    self.candle_states[n]["low"] = min(self.candle_states[n]["low"], price)
                    self.candle_states[n]["close"] = price

                if self.candle_counter % n == 0:
                    self._emit_candle(n)


        except Exception as e:
            print(e)

    
    def _emit_candle(self, n):
        candle = self.candle_states[n]
        self.callbacks[n](candle)
        self.candle_states[n]["reset"] = True