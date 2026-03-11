"""
This script is used to stream ticks from databento and build 1s candles in real-time.
It keeps the candles in-memory and writes them to a csv file at the end of each session.
"""

import os
import time
import threading
from collections import deque
import databento as db
import dotenv

dotenv.load_dotenv()

DATABENTO_API_KEY = os.getenv("DATABENTO_API_KEY")
dataset = "GLBX.MDP3"
trigger_callback = lambda: ()

candles = deque()
current_candle = {
    "timestamp": None,
    "open": None,
    "high": None,
    "low": None,
    "close": None,
    "price_levels": {}
}
_lock = threading.Lock()


def _snapshot_candle(candle):
    """Return a deep-enough copy of a candle so archived entries are immutable."""
    return {**candle, "price_levels": dict(candle["price_levels"])}


def reset_candle(tick_ts, new_open):
    """Archive the completed candle and initialise a fresh one."""
    sc = _snapshot_candle(current_candle)
    candles.append(sc)
    trigger_callback(sc)
    current_candle["timestamp"] = tick_ts
    current_candle["open"] = new_open
    current_candle["high"] = new_open
    current_candle["low"] = new_open
    current_candle["close"] = new_open
    current_candle["price_levels"] = {}


def handle_data(data):
    # Use integer division to avoid float precision errors at candle boundaries.
    tick_ts = data.ts_event // 1_000_000_000
    p = data.price
    # side: "A" = ask resting (buyer aggressor) → buy; "B" = bid resting (seller aggressor) → sell
    side = -1 if data.side == "A" else 1
    qty = data.size

    with _lock:
        if current_candle["timestamp"] is None:
            # First tick ever: seed the candle fully before any max/min calls.
            current_candle["timestamp"] = tick_ts
            current_candle["open"] = p
            current_candle["high"] = p
            current_candle["low"] = p
            current_candle["close"] = p
        elif tick_ts > current_candle["timestamp"]:
            reset_candle(tick_ts, p)

        # Accumulate into the current second.
        current_candle["close"] = p
        current_candle["high"] = max(current_candle["high"], p)
        current_candle["low"] = min(current_candle["low"], p)
        c_vol = current_candle["price_levels"].get(p, [0, 0])
        d_buy  = qty if side ==  1 else 0
        d_sell = qty if side == -1 else 0
        current_candle["price_levels"][p] = [c_vol[0] + d_buy, c_vol[1] + d_sell]


def start(cb):
    global trigger_callback
    trigger_callback = cb
    client = db.Live(DATABENTO_API_KEY)
    client.subscribe(
        dataset=dataset,
        schema="trades",
        symbols="NQ.v.0",
        stype_in="continuous",
    )
    client.add_callback(handle_data)
    client.start()
