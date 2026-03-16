"""
Backfill: fetch NQ trades for a given session window, aggregate into 1-second
candles, and write the result to a CSV file.

Output candle format is identical to datafeed.py:
    { timestamp, open, high, low, close, price_levels, absorption }

Numba JIT emulates the live datafeed.handle_data / reset_candle loop at speed.
price_levels is built via a pandas groupby after the JIT pass and stored as a
JSON string in the CSV (the only serialisation-safe option for a dict column).
"""

import json
import os

import databento as db
import dotenv
import numpy as np
import numba
import pandas as pd

dotenv.load_dotenv()

# ── Configuration ──────────────────────────────────────────────────────────────
SESSION_DATE  = "2026-03-09"   # YYYY-MM-DD (UTC calendar date)
SESSION_START = "14:30:00"     # UTC – NYSE/CME RTH open  (≡ 09:30 ET)
SESSION_END   = "16:00:00"     # UTC

SYMBOL  = "NQ.v.0"
DATASET = "GLBX.MDP3"
OUT_DIR = os.path.dirname(os.path.abspath(__file__))

# ── Credentials ────────────────────────────────────────────────────────────────
DATABENTO_API_KEY = os.getenv("DATABENTO_API_KEY")


# ── Numba JIT: candle aggregation ──────────────────────────────────────────────
@numba.njit(cache=True)
def _aggregate_candles(ts_ns, prices, sides, sizes):
    """
    Emulates datafeed.handle_data + datafeed.reset_candle tick-by-tick.

    Parameters
    ----------
    ts_ns  : int64[:]    nanosecond event timestamps (ts_event)
    prices : float64[:]  trade prices (already scaled to real $-value)
    sides  : int8[:]     +1 = buy-aggressor (B resting / ask hit),
                         -1 = sell-aggressor (A resting / bid hit),
                          0 = unknown
    sizes  : int64[:]    trade sizes (contracts)

    Returns
    -------
    Candle arrays (one entry per completed 1-second candle):
        out_ts, out_open, out_high, out_low, out_cls, out_buy, out_sell
    tick_candle_ts : int64[n]
        For every input tick, the Unix-second of the candle it was assigned to.
        Used by the Python layer to reconstruct price_levels per candle.
    """
    n = len(ts_ns)

    # Candle output arrays – worst-case size.
    out_ts   = np.empty(n, dtype=np.int64)
    out_open = np.empty(n, dtype=np.float64)
    out_high = np.empty(n, dtype=np.float64)
    out_low  = np.empty(n, dtype=np.float64)
    out_cls  = np.empty(n, dtype=np.float64)
    out_buy  = np.empty(n, dtype=np.int64)
    out_sell = np.empty(n, dtype=np.int64)

    # Per-tick candle assignment (returned to Python for price_levels groupby).
    tick_candle_ts = np.empty(n, dtype=np.int64)

    ci = np.int64(0)

    # Seed from first tick (mirrors "First tick ever" branch in datafeed.py).
    cur_ts = ts_ns[0] // np.int64(1_000_000_000)
    c_open = prices[0]
    c_high = prices[0]
    c_low  = prices[0]
    c_cls  = prices[0]
    if sides[0] == np.int8(1):
        c_buy  = sizes[0]
        c_sell = np.int64(0)
    elif sides[0] == np.int8(-1):
        c_buy  = np.int64(0)
        c_sell = sizes[0]
    else:
        c_buy  = np.int64(0)
        c_sell = np.int64(0)
    tick_candle_ts[0] = cur_ts

    for i in range(1, n):
        tick_ts = ts_ns[i] // np.int64(1_000_000_000)
        p = prices[i]
        s = sides[i]
        q = sizes[i]

        if tick_ts > cur_ts:
            # ── flush completed candle (mirrors reset_candle) ──────────────
            out_ts[ci]   = cur_ts
            out_open[ci] = c_open
            out_high[ci] = c_high
            out_low[ci]  = c_low
            out_cls[ci]  = c_cls
            out_buy[ci]  = c_buy
            out_sell[ci] = c_sell
            ci += np.int64(1)

            # ── seed new candle ────────────────────────────────────────────
            cur_ts = tick_ts
            c_open = p
            c_high = p
            c_low  = p
            c_cls  = p
            c_buy  = np.int64(0)
            c_sell = np.int64(0)

        # ── tag tick with its candle second ───────────────────────────────
        tick_candle_ts[i] = cur_ts

        # ── accumulate tick into current second ────────────────────────────
        c_cls = p
        if p > c_high:
            c_high = p
        if p < c_low:
            c_low = p
        if s == np.int8(1):
            c_buy += q
        elif s == np.int8(-1):
            c_sell += q

    # Flush the final in-progress candle.
    out_ts[ci]   = cur_ts
    out_open[ci] = c_open
    out_high[ci] = c_high
    out_low[ci]  = c_low
    out_cls[ci]  = c_cls
    out_buy[ci]  = c_buy
    out_sell[ci] = c_sell
    ci += np.int64(1)

    return (
        out_ts[:ci],
        out_open[:ci],
        out_high[:ci],
        out_low[:ci],
        out_cls[:ci],
        out_buy[:ci],
        out_sell[:ci],
        tick_candle_ts,
    )


NQ_TICK = 0.25   # NQ minimum tick size in index points (prices in CSV are real dollars)


# ── Numba JIT: absorption (mirrors datafeed._calc_absorption exactly) ──────────
@numba.njit(cache=True)
def _calc_absorptions(opens, closes, buy_vols, sell_vols):
    """
    A = −I × (|I| + max(0, −sign(I) × Δticks))

      I       = (buy−sell)/(buy+sell)  ∈ [−1,+1]
      Δticks  = (close−open) / NQ_TICK   (signed, dimensionless)

    Sign convention:
      A < 0  →  buy-side absorption  (buyers failing → short signal)
      A > 0  →  sell-side absorption (sellers failing → long signal)

    Backfill prices are real dollars; datafeed uses fixed-point / NQ_TICK_FP.
    Both yield identical Δticks and therefore identical absorption values.
    """
    n = len(opens)
    absorptions = np.empty(n, dtype=np.float64)

    for i in range(n):
        buy   = buy_vols[i]
        sell  = sell_vols[i]
        total = buy + sell
        if total > 0:
            I           = (buy - sell) / total
            delta_ticks = (closes[i] - opens[i]) / NQ_TICK
            abs_I       = abs(I)
            if I > 0.0:
                contrary = -delta_ticks          # ticks against buy imbalance
            elif I < 0.0:
                contrary = delta_ticks           # ticks against sell imbalance
            else:
                contrary = 0.0
            if contrary < 0.0:
                contrary = 0.0
            absorptions[i] = -I * (abs_I + contrary)
        else:
            absorptions[i] = 0.0

    return absorptions


# ── Main routine ───────────────────────────────────────────────────────────────
def backfill():
    start_str = f"{SESSION_DATE}T{SESSION_START}Z"
    end_str   = f"{SESSION_DATE}T{SESSION_END}Z"

    print(f"[backfill] Fetching {SYMBOL} trades  {start_str} → {end_str}")
    client = db.Historical(DATABENTO_API_KEY)
    raw = client.timeseries.get_range(
        dataset=DATASET,
        schema="trades",
        symbols=SYMBOL,
        stype_in="continuous",
        start=start_str,
        end=end_str,
    )

    df = raw.to_df()
    print(f"[backfill] {len(df):,} ticks received.")

    if df.empty:
        print("[backfill] No data – check SESSION_DATE, symbol, and API key.")
        return

    # ── Extract arrays ─────────────────────────────────────────────────────────
    # databento sets ts_event as the DatetimeIndex; .astype(int64) = ns-since-epoch.
    ts_ns = df.index.astype(np.int64).to_numpy()

    # Prices come pre-scaled to real dollar values (e.g. NQ ~22 000).
    # Guard: if they're still in fixed-point (>1e9), divide down.
    prices = df["price"].to_numpy(dtype=np.float64)
    if prices.max() > 1e9:
        prices /= 1_000_000_000.0

    sizes = df["size"].to_numpy(dtype=np.int64)

    # Encode side to int8, mirroring datafeed.py:
    #   "A" → ask resting, sell-aggressor → -1
    #   "B" → bid resting, buy-aggressor  → +1
    side_raw = df["side"].to_numpy()
    sides = np.where(side_raw == "B", np.int8(1),
            np.where(side_raw == "A", np.int8(-1), np.int8(0))).astype(np.int8)

    # Guarantee chronological order.
    order  = np.argsort(ts_ns, kind="stable")
    ts_ns  = ts_ns[order]
    prices = prices[order]
    sides  = sides[order]
    sizes  = sizes[order]

    # ── JIT aggregation ────────────────────────────────────────────────────────
    print("[backfill] Aggregating into 1-second candles (numba JIT) …")
    (candle_ts, opens, highs, lows, closes,
     buy_vols, sell_vols, tick_candle_ts) = _aggregate_candles(
        ts_ns, prices, sides, sizes
    )

    # ── Build price_levels per candle ──────────────────────────────────────────
    # price_levels mirrors datafeed.py: { price: [buy_vol, sell_vol], ... }
    # We use a pandas groupby on the per-tick candle assignment produced by JIT.
    print("[backfill] Building price_levels …")
    buy_arr  = np.where(sides == np.int8(1),  sizes, np.int64(0))
    sell_arr = np.where(sides == np.int8(-1), sizes, np.int64(0))

    tick_df = pd.DataFrame({
        "candle_ts": tick_candle_ts,
        "price":     prices,
        "buy":       buy_arr,
        "sell":      sell_arr,
    })

    pl_grouped = (
        tick_df.groupby(["candle_ts", "price"], sort=False)[["buy", "sell"]]
        .sum()
    )

    # Build a dict-of-dicts: { candle_ts_int: { price: [buy, sell] } }
    pl_by_candle: dict[int, dict] = {}
    for (cts, price), row in pl_grouped.iterrows():
        bucket = pl_by_candle.setdefault(int(cts), {})
        bucket[price] = [int(row["buy"]), int(row["sell"])]

    # ── JIT absorption ─────────────────────────────────────────────────────────
    print("[backfill] Computing absorption …")
    absorptions = _calc_absorptions(opens, closes, buy_vols, sell_vols)

    # ── Assemble candles in exact datafeed.py format ───────────────────────────
    # { timestamp (unix-s int), open, high, low, close, price_levels, absorption }
    out = pd.DataFrame({
        "timestamp":    candle_ts,               # Unix seconds integer
        "open":         opens,
        "high":         highs,
        "low":          lows,
        "close":        closes,
        "price_levels": [
            json.dumps(pl_by_candle.get(int(t), {})) for t in candle_ts
        ],
        "absorption":   absorptions,
    })

    out_path = os.path.join(OUT_DIR, f"backfill_{SESSION_DATE}.csv")
    out.to_csv(out_path, index=False)
    print(f"[backfill] Saved {len(out)} candles → {out_path}")


if __name__ == "__main__":
    for date in ["2026-03-09", "2026-03-10", "2026-03-11", "2026-03-12", "2026-03-13"]:
        SESSION_DATE = date
        backfill()
