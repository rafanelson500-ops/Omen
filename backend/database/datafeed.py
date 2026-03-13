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
minimum_update_interval = 50_000_000  # 50 ms in nanoseconds (~20 updates/sec max)

trigger_callback = lambda: ()
update_callback = lambda: ()

candles = deque()
default_candle = {
    "timestamp": None,
    "open": None,
    "high": None,
    "low": None,
    "close": None,
    "price_levels": {},
    "absorption": 0.0,
}
current_candle = default_candle.copy()
last_tick_time = 0
_lock = threading.Lock()


def _snapshot_candle(candle):
    """Return a deep-enough copy of a candle so archived entries are immutable."""
    return {**candle, "price_levels": dict(candle["price_levels"])}


def _calc_absorption(price_levels: dict) -> float:
    """I = (buy - sell) / (buy + sell) for the completed candle."""
    buy  = sum(v[0] for v in price_levels.values())
    sell = sum(v[1] for v in price_levels.values())
    total = buy + sell
    return (buy - sell) / total if total else 0.0


def reset_candle(tick_ts, new_open):
    global current_candle
    """Archive the completed candle and initialise a fresh one."""
    sc = _snapshot_candle(current_candle)
    sc["absorption"] = _calc_absorption(sc["price_levels"])
    candles.append(sc)
    trigger_callback(sc)
    current_candle = default_candle.copy()


def handle_data(data):
    global last_tick_time
    # Use integer division to avoid float precision errors at candle boundaries.
    tick_ts = data.ts_event // 1_000_000_000
    p = data.price
    # side: "A" = ask resting (buyer aggressor) → buy; "B" = bid resting (seller aggressor) → sell
    side = -1 if data.side == "A" else 1
    qty = data.size

    emit_update = False
    snapshot = None

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

        if data.ts_event - last_tick_time > minimum_update_interval:
            emit_update = True
            snapshot = _snapshot_candle(current_candle)
            last_tick_time = data.ts_event  # keep units in nanoseconds

    # Emit outside the lock so socket I/O never blocks tick ingestion.
    if emit_update:
        update_callback(snapshot)


def start(cb, update_cb):
    global trigger_callback, update_callback
    trigger_callback = cb
    update_callback = update_cb
    client = db.Live(DATABENTO_API_KEY)
    client.subscribe(
        dataset=dataset,
        schema="trades",
        symbols="NQ.v.0",
        stype_in="continuous",
    )
    client.add_callback(handle_data)
    client.start()
