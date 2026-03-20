import os
from collections import deque
import databento as db
import dotenv

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
        self.client.add_callback(self._on_tick)
        self.client.start()

    def subscribe(self, callback):
        self.callbacks.append(callback)

    def _on_tick(self, tick):
        try:
            price = tick.pretty_price
            side = -1 if tick.side == "A" else 1
            size = tick.size
            ts = tick.ts_event / 1_000_000_000

            clean_tick = {
                "price": price,
                "side": side,
                "size": size,
                "ts": ts
            }

            for callback in self.callbacks:
                callback(clean_tick)
        except Exception as e:
            pass
