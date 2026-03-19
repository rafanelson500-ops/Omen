"""
Stream ticks from databento and build candles in real-time across multiple
timeframes (1s, 1m, 15m) simultaneously.

Each timeframe maintains its own in-memory deque of completed candles and fires
a callback whenever a candle closes.  All state is protected by a single lock.
"""

import os
import threading
from collections import deque
import databento as db
import dotenv

dotenv.load_dotenv()

DATABENTO_API_KEY = os.getenv("DATABENTO_API_KEY")
dataset = "GLBX.MDP3"
symbol = "NQM6"

class Datafeed:
    def __init__(self):
        print("Initializing Datafeed")
        self.client = db.Live(DATABENTO_API_KEY)
    
    def start(self):
        self.client.subscribe(
            dataset=dataset,
            schema="trades",
            symbols=symbol,
            stype_in="raw_symbol",
        )
        self.client.subscribe(
            dataset=dataset,
            schema="trades",
            symbols=symbol,
            stype_in="raw_symbol",
        )
        self.client.add_callback(self.on_message)
        self.client.start()

    def on_message(self, message):
        print("\n",message)