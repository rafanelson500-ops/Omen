"""Databento ES continuous front-month OHLCV-1s fetch, cache, and resample."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from pathlib import Path

import databento as db
import pandas as pd
from rich.console import Console

from cheese.config import (
    DATA_DIR,
    DATABENTO_DATASET,
    ES_CONTINUOUS_SYMBOL,
    ET,
    MARKET_CACHE,
    UTC,
)

MARKET_LIVE_CACHE = DATA_DIR / "market_live"

console = Console()

# Databento historical data has a ~15 min publishing delay on GLBX.MDP3.
# Clamp the requested end timestamp to now - DATA_DELAY so the API never 422s.
DATA_DELAY = timedelta(minutes=35)


def _clamp_end(end: date) -> pd.Timestamp:
    """Return the end timestamp in UTC, capped at now - DATA_DELAY."""
    requested = pd.Timestamp(end + pd.Timedelta(days=1), tz=ET).tz_convert(UTC)
    max_allowed = pd.Timestamp.now(tz=UTC) - DATA_DELAY
    if requested > max_allowed:
        console.print(
            f"[dim]market: clamping end {requested.isoformat()} -> "
            f"{max_allowed.isoformat()} (Databento 15m delay)[/]"
        )
        return max_allowed
    return requested


def _cache_path(start: date, end: date) -> Path:
    return MARKET_CACHE / f"ES_c_0_ohlcv1s_{start.isoformat()}_{end.isoformat()}.parquet"


def _start_utc(start: date) -> pd.Timestamp:
    """Start timestamp pinned to 09:25 ET on `start`, converted to UTC."""
    return pd.Timestamp(datetime.combine(start, time(9, 25)), tz=ET).tz_convert(UTC)


def estimate_cost(start: date, end: date, api_key: str) -> float:
    """Return Databento's estimated USD cost for the pull (no download)."""
    client = db.Historical(api_key)
    cost = client.metadata.get_cost(
        dataset=DATABENTO_DATASET,
        symbols=[ES_CONTINUOUS_SYMBOL],
        stype_in="continuous",
        schema="ohlcv-1s",
        start=_start_utc(start),
        end=_clamp_end(end),
    )
    return float(cost)


def fetch(
    start: date,
    end: date,
    api_key: str,
    force: bool = False,
) -> Path:
    """Fetch ES.c.0 ohlcv-1s for [start, end] inclusive. Cache as parquet.

    Note: Databento returns UTC timestamps; we convert to America/New_York and
    keep RTH filtering for a separate step (downstream).
    """
    cache = _cache_path(start, end)
    if cache.exists() and not force:
        console.print(f"[dim]market: using cache {cache.name}[/]")
        return cache

    client = db.Historical(api_key)
    start_utc = _start_utc(start)
    end_utc = _clamp_end(end)

    console.print(
        f"[cyan]Databento[/] pulling ohlcv-1s {ES_CONTINUOUS_SYMBOL} "
        f"{start.isoformat()} -> {end.isoformat()} ..."
    )
    data = client.timeseries.get_range(
        dataset=DATABENTO_DATASET,
        symbols=[ES_CONTINUOUS_SYMBOL],
        stype_in="continuous",
        schema="ohlcv-1s",
        start=start_utc,
        end=end_utc,
    )
    df = data.to_df()
    if df.empty:
        raise RuntimeError("Databento returned no rows; check symbol / dates / entitlements.")

    df.index = pd.to_datetime(df.index, utc=True).tz_convert(ET)
    df.index.name = "timestamp"
    keep = [c for c in ("open", "high", "low", "close", "volume") if c in df.columns]
    df = df[keep].astype({"open": "float64", "high": "float64", "low": "float64", "close": "float64"})
    df.to_parquet(cache)
    console.print(f"[green]market: saved {len(df):,} rows -> {cache.name}[/]")
    return cache


def load(start: date, end: date, freq: str = "1min", rth_only: bool = True) -> pd.DataFrame:
    """Load cached ES data and resample to desired frequency.

    `freq` can be "1s" (no resample), "1min", "5min", etc. If `rth_only` we
    clip to 09:30 <= t < 16:00 America/New_York for RTH trading.
    """
    cache = _cache_path(start, end)
    if not cache.exists():
        raise FileNotFoundError(f"No market cache for {start}..{end}. Run fetch_market.py first.")
    df = pd.read_parquet(cache)
    df.index = pd.to_datetime(df.index, utc=True).tz_convert(ET)
    df = df.sort_index()

    if rth_only:
        t = df.index.time
        df = df[(t >= time(9, 30)) & (t < time(16, 0))]

    if freq != "1s":
        df = (
            df.resample(freq, label="right", closed="right")
              .agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
              .dropna(subset=["close"])
        )
        # resample can create bars spanning the overnight gap; drop those
        t = df.index.time
        df = df[(t > time(9, 30)) & (t <= time(16, 0))]

    return df


def _live_day_path(d: date) -> Path:
    return MARKET_LIVE_CACHE / f"{d.isoformat()}.parquet"


def live_day_available() -> list[date]:
    """Return sorted list of dates for which data/market_live/<d>.parquet exists."""
    if not MARKET_LIVE_CACHE.exists():
        return []
    out: list[date] = []
    for p in MARKET_LIVE_CACHE.glob("*.parquet"):
        try:
            out.append(date.fromisoformat(p.stem))
        except ValueError:
            continue
    return sorted(out)


def load_live_day(d: date, freq: str = "1min", rth_only: bool = True) -> pd.DataFrame:
    """Load one day of ES 1s OHLCV from the live daemon cache and resample.

    Mirrors ``load()`` but reads ``data/market_live/<YYYY-MM-DD>.parquet`` (written
    by ``scripts/data_daemon.py``) instead of the historical Databento range cache.
    """
    path = _live_day_path(d)
    if not path.exists():
        raise FileNotFoundError(
            f"No market_live parquet for {d}. Run the data daemon or check {path}."
        )
    df = pd.read_parquet(path)
    df.index = pd.to_datetime(df.index, utc=True).tz_convert(ET)
    df = df.sort_index()

    if rth_only:
        t = df.index.time
        df = df[(t >= time(9, 30)) & (t < time(16, 0))]

    if freq != "1s":
        df = (
            df.resample(freq, label="right", closed="right")
              .agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
              .dropna(subset=["close"])
        )
        t = df.index.time
        df = df[(t > time(9, 30)) & (t <= time(16, 0))]

    return df
