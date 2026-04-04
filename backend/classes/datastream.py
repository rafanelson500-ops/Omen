from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

import databento as db
import dotenv
import numpy as np
import pandas as pd

dotenv.load_dotenv()

DATABENTO_API_KEY = os.getenv("DATABENTO_API_KEY")
dataset = "GLBX.MDP3"
symbol = "NQ.v.0"


def _ts_event_to_time_us(ts_event: int, n) -> int:
    """Match historical(): nanoseconds → integer microseconds (JSON-safe in browser)."""
    return int(ts_event) / n


def _trade_price(record: Any) -> float:
    if hasattr(record, "pretty_price"):
        return float(record.pretty_price)
    return float(int(record.price)) * 1e-9


def _trade_size(record: Any) -> int:
    return int(getattr(record, "size", 0))


def _side_sign(side: Any) -> int:
    return 1 if side == "B" else -1


def _agg_bar_from_ticks(ticks: list[tuple[float, int, int, int]]) -> dict[str, Any]:
    """ticks: (price, time_us, size, side_sign) per trade."""
    prices = [t[0] for t in ticks]
    sizes = [t[2] for t in ticks]
    deltas = [t[2] * t[3] for t in ticks]
    return {
        "time": ticks[0][1],
        "open": prices[0],
        "high": max(prices),
        "low": min(prices),
        "close": prices[-1],
        "volume": sum(sizes),
        "delta": sum(deltas),
    }


class Datastream:
    def __init__(
        self,
        emit_tick: Callable[[dict[str, Any]], None] | None = None,
        emit_medium_tick: Callable[[dict[str, Any]], None] | None = None,
        emit_long_tick: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        print("Initializing Datastream Engine")
        self.short_df = pd.DataFrame()
        self.medium_df = pd.DataFrame()
        self.long_df = pd.DataFrame()

        self.emit_tick = emit_tick
        self.emit_medium_tick = emit_medium_tick
        self.emit_long_tick = emit_long_tick

        self._buf10: list[tuple[float, int, int, int]] = []
        self._buf100: list[tuple[float, int, int, int]] = []

    def historical(self, start_date, end_date):
        client = db.Historical(DATABENTO_API_KEY)
        print(f"Getting ticks from {start_date} to {end_date}")
        ticks = client.timeseries.get_range(
            dataset=dataset,
            symbols=symbol,
            stype_in="continuous",
            start=start_date,
            end=end_date,
            schema="trades",
        )
        short_df = ticks.to_df()[["ts_event", "size", "price", "side"]].dropna()
        short_df.index = np.arange(1, len(short_df) + 1)
        short_df["side"] = np.where(short_df["side"] == "B", 1, -1)

        short_df["time"] = short_df["ts_event"].astype("int64") * 1e-9
        short_df["open"] = short_df["price"]
        short_df["high"] = short_df["price"]
        short_df["low"] = short_df["price"]
        short_df["close"] = short_df["price"]
        short_df["volume"] = short_df["size"]
        short_df["delta"] = short_df["size"] * short_df["side"]

        short_df.drop(columns=["price", "ts_event", "size", "side"], inplace=True)

        short_df = short_df.drop_duplicates(subset=["time"], keep="last")

        medium_df = aggregate_ticks(short_df, 10)
        long_df = aggregate_ticks(short_df, 100)

        self.short_df = short_df
        self.medium_df = medium_df
        self.long_df = long_df

        return short_df, medium_df, long_df

    def live(self) -> None:
        """Blocks until the live client stops; run in a background thread."""
        if not self.emit_tick or not self.emit_medium_tick or not self.emit_long_tick:
            raise RuntimeError("Live mode requires emit_tick, emit_medium_tick, emit_long_tick callbacks")

        def on_record(record: Any) -> None:
            if not hasattr(record, "ts_event"):
                return
            if not hasattr(record, "price") and not hasattr(record, "pretty_price"):
                return
            try:
                price = _trade_price(record)
                ts_us = _ts_event_to_time_us(record.ts_event, 1e9)
                size = _trade_size(record)
                sgn = _side_sign(record.side)
            except Exception:
                return

            tick_row = {
                "time": ts_us,
                "open": price,
                "high": price,
                "low": price,
                "close": price,
                "volume": size,
                "delta": size * sgn,
            }


            tup = (price, ts_us, size, sgn)
            self._buf100.append(tup)
            if len(self._buf100) >= 100:
                self.emit_long_tick(_agg_bar_from_ticks(self._buf100))
                self._buf100.clear()

            self._buf10.append(tup)
            if len(self._buf10) >= 10:
                self.emit_medium_tick(_agg_bar_from_ticks(self._buf10))
                self._buf10.clear()

            self.emit_tick(tick_row)

        client = db.Live(DATABENTO_API_KEY)
        print("Getting live ticks")
        client.subscribe(
            dataset=dataset,
            symbols=symbol,
            stype_in="continuous",
            schema="trades",
        )
        client.add_callback(on_record)
        client.start()


def aggregate_ticks(df, n):
    """
    Non-overlapping n-tick bars on **row order** (ticks 0..n-1, n..2n-1, …).

    Matches ``Datastream.live`` buffer flushes. Trailing ticks that do not fill a
    full bar are **dropped** (live never emits a partial bar).

    .. note::
        Historical data used ``df.index // n`` with a 1-based index, so the first
        bar had only *n−1* ticks and bar boundaries disagreed with live and with
        ``master`` VWAP (which uses these boundaries).
    """
    df = df.copy().reset_index(drop=True)
    m = (len(df) // n) * n
    if m == 0:
        return pd.DataFrame(
            columns=["time", "open", "high", "low", "close", "delta", "volume"]
        )
    sub = df.iloc[:m]
    gid = np.arange(m, dtype=np.int64) // n
    return (
        sub.groupby(gid, sort=True)
        .agg(
            {
                "time": "first",
                "open": "first",
                "high": "max",
                "low": "min",
                "close": "last",
                "delta": "sum",
                "volume": "sum",
            }
        )
        .reset_index(drop=True)
    )
