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

_default_candle = {
    "timestamp": None,
    "open": None,
    "high": None,
    "low": None,
    "close": None,
    "price_levels": {},
    "absorption": 0.0,
}

# Each timeframe gets its own independent candle state.
# `interval` is the period in nanoseconds used to floor-align tick timestamps.
timeframes: dict = {
    "1s": {
        "candles":        deque(),
        "current_candle": {**_default_candle, "price_levels": {}},
        "callback":       None,   # callable(tf, candle) — set by start()
        "interval":       1 * 1_000_000_000,
    },
    "1m": {
        "candles":        deque(),
        "current_candle": {**_default_candle, "price_levels": {}},
        "callback":       None,
        "interval":       60 * 1_000_000_000,
    },
    "5m": {
        "candles":        deque(),
        "current_candle": {**_default_candle, "price_levels": {}},
        "callback":       None,
        "interval":       5 * 60 * 1_000_000_000,
    },
}

tick_callback = None

_lock = threading.Lock()


# ── Helpers ────────────────────────────────────────────────────────────────────

def _snapshot_candle(candle: dict) -> dict:
    """Return a deep-enough copy so archived entries are immutable."""
    return {**candle, "price_levels": dict(candle["price_levels"])}


NQ_TICK    = 0.25                            # NQ minimum tick size in index points
NQ_TICK_FP = int(NQ_TICK * 1_000_000_000)   # same value in fixed-point units


def _calc_absorption(sc: dict) -> float:
    """
    A = −I × (|I| + max(0, −sign(I) × Δticks))

      I       = (buy − sell) / (buy + sell)  ∈ [−1, +1]
      Δticks  = (close − open) / tick_size   (signed, dimensionless)

    Sign convention:
      A < 0  →  buy-side absorption  (buyers failing → short signal)
      A > 0  →  sell-side absorption (sellers failing → long signal)

    Prices in the live feed are fixed-point int64 (1e9 factor), so tick size is
    expressed in fixed-point units for the division.
    """
    price_levels = sc["price_levels"]
    buy   = sum(v[0] for v in price_levels.values())
    sell  = sum(v[1] for v in price_levels.values())
    total = buy + sell
    if not total:
        return 0.0
    I           = (buy - sell) / total
    delta_ticks = (sc["close"] - sc["open"]) / NQ_TICK_FP
    abs_I       = abs(I)
    sign_I      = (1.0 if I > 0.0 else -1.0) if I != 0.0 else 0.0
    contrary    = max(0.0, -sign_I * delta_ticks)
    return -I * (abs_I + contrary)


# ── Candle lifecycle ───────────────────────────────────────────────────────────

def _close_candle(tf: str, tick_slot: int, new_open: int) -> tuple:
    """
    Archive the completed candle for `tf` and seed a fresh one aligned to
    `tick_slot`.  Returns ``(tf, completed_candle)`` so the caller can fire
    the callback **after** releasing `_lock`.

    Must be called with `_lock` already held.
    """
    tf_data        = timeframes[tf]
    current_candle = tf_data["current_candle"]

    sc = _snapshot_candle(current_candle)
    sc["absorption"] = _calc_absorption(sc)
    tf_data["candles"].append(sc)

    tf_data["current_candle"] = {
        **_default_candle,
        "price_levels": {},
        "timestamp":    tick_slot,
        "open":         new_open,
        "high":         new_open,
        "low":          new_open,
        "close":        new_open,
    }

    return (tf, sc)


def handle_data(data) -> None:
    """Process a single trade tick and update every timeframe's candle."""
    tick_ts = data.ts_event
    p       = data.price
    # "A" = ask resting → buyer aggressor → buy side
    # "B" = bid resting → seller aggressor → sell side
    side = 1 if data.side == "A" else -1
    qty  = data.size

    if tick_callback is not None:
        tick_callback({
            "timestamp": tick_ts,
            "price": p,
            "side": side,
            "size": qty,
        })

    closed: list[tuple] = []   # (tf, candle) pairs to dispatch after lock release

    with _lock:
        for tf, tf_data in timeframes.items():
            interval       = tf_data["interval"]
            current_candle = tf_data["current_candle"]

            # Floor the tick's timestamp to the start of its candle slot.
            tick_slot = (tick_ts // interval) * interval

            if current_candle["timestamp"] is None:
                # First tick ever for this timeframe: seed the candle.
                current_candle["timestamp"] = tick_slot
                current_candle["open"]      = p
                current_candle["high"]      = p
                current_candle["low"]       = p
                current_candle["close"]     = p

            elif tick_slot > current_candle["timestamp"]:
                # Tick belongs to a new candle period — close the old one.
                closed.append(_close_candle(tf, tick_slot, p))
                # Re-bind after reset so the accumulation below is correct.
                current_candle = tf_data["current_candle"]

            # Accumulate tick into the current candle for this timeframe.
            current_candle["close"] = p
            current_candle["high"]  = max(current_candle["high"], p)
            current_candle["low"]   = min(current_candle["low"],  p)
            c_vol  = current_candle["price_levels"].get(p, [0, 0])
            d_buy  = qty if side ==  1 else 0
            d_sell = qty if side == -1 else 0
            current_candle["price_levels"][p] = [c_vol[0] + d_buy, c_vol[1] + d_sell]

    # Fire callbacks outside the lock so I/O-bound handlers (SocketIO, DB
    # writes, etc.) don't stall incoming ticks during high-volume periods.
    for tf, sc in closed:
        cb = timeframes[tf]["callback"]
        if cb is not None:
            cb(tf, sc)


# ── Entry point ────────────────────────────────────────────────────────────────

def start(callbacks: "dict[str, callable] | callable", tick_cb: callable) -> None:
    """
    Start the live datafeed.

    Parameters
    ----------
    callbacks : dict or callable
        * ``dict[str, callable(candle)]`` – per-timeframe callbacks.
          Keys are timeframe names (``"1s"``, ``"1m"``, ``"15m"``).
          Each callable receives only the completed candle dict.
        * A single ``callable(tf: str, candle: dict)`` – called for every
          timeframe, receiving the timeframe name and the completed candle.

    Examples
    --------
    # Same handler for all timeframes:
    start(lambda tf, candle: print(tf, candle))

    # Different handler per timeframe:
    start({"1s": on_1s_candle, "1m": on_1m_candle, "15m": on_15m_candle})
    """
    global tick_callback
    tick_callback = tick_cb

    if callable(callbacks):
        # Wrap the broadcast callable so the internal signature stays (tf, candle).
        for tf in timeframes:
            _cb = callbacks
            timeframes[tf]["callback"] = _cb
    elif isinstance(callbacks, dict):
        for tf, cb in callbacks.items():
            if tf in timeframes:
                # Wrap per-TF callback to inject `tf` for internal consistency.
                def _make_cb(cb_=cb, tf_=tf):
                    return lambda _tf, candle: cb_(candle)
                timeframes[tf]["callback"] = _make_cb()
    else:
        raise TypeError("callbacks must be a callable or a dict of callables")

    client = db.Live(DATABENTO_API_KEY)
    client.subscribe(
        dataset=dataset,
        schema="trades",
        symbols="NQ.v.0",
        stype_in="continuous",
    )
    client.add_callback(handle_data)
    client.start()
