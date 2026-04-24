"""GEXbot orderflow fetching, caching, loading, and resampling.

Endpoint pattern (from api.gex.bot v2):
    GET /v2/hist/ES_SPX/orderflow/orderflow/{YYYY-M-D}?noredirect
        Authorization: Bearer <GEXBOT_API_KEY>
    -> JSON { "url": "<presigned blob url to .json.gz>" }
    -> GET that url -> gzipped JSON array of 1s records

Each record carries the schema from the user-provided sample:
    timestamp, ticker, spot,
    z_mlgamma, z_msgamma, o_mlgamma, o_msgamma,
    zero_mcall, zero_mput, one_mcall, one_mput,
    zcvr, ocvr, zgr, ogr,
    zvanna, ovanna, zcharm, ocharm,
    agg_dex, one_agg_dex, agg_call_dex, one_agg_call_dex,
    agg_put_dex, one_agg_put_dex,
    net_dex, one_net_dex, net_call_dex, one_net_call_dex,
    net_put_dex, one_net_put_dex,
    dexoflow, gexoflow, cvroflow, one_dexoflow, one_gexoflow, one_cvroflow

Cached per-day as parquet at backend/data/gex/{YYYY-MM-DD}.parquet.
"""
from __future__ import annotations

import gzip
import io
import os
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable

import pandas as pd
import pandas_market_calendars as mcal
import requests
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn

from cheese.config import GEX_CACHE, ET

console = Console()

GEXBOT_URL = "https://api.gex.bot/v2/hist/ES_SPX/orderflow/orderflow/{date}?noredirect"
USER_AGENT = "cheese-trading/1.0.0"

# Column groupings for resample
LEVEL_COLS = [
    "spot",
    "z_mlgamma", "z_msgamma", "o_mlgamma", "o_msgamma",
    "zero_mcall", "zero_mput", "one_mcall", "one_mput",
]
STATE_COLS = [
    "zcvr", "ocvr", "zgr", "ogr",
    "zvanna", "ovanna", "zcharm", "ocharm",
    "agg_dex", "agg_call_dex", "agg_put_dex",
    "net_dex", "net_call_dex", "net_put_dex",
]
FLOW_COLS = [
    "dexoflow", "gexoflow", "cvroflow",
    "one_dexoflow", "one_gexoflow", "one_cvroflow",
    "one_agg_dex", "one_agg_call_dex", "one_agg_put_dex",
    "one_net_dex", "one_net_call_dex", "one_net_put_dex",
]


# ---------- Trading day helpers ---------------------------------------------
_NYSE = mcal.get_calendar("NYSE")


def rth_sessions(start: date, end: date) -> list[date]:
    """Return list of RTH trading dates in [start, end] inclusive (US equities)."""
    sched = _NYSE.schedule(start_date=pd.Timestamp(start), end_date=pd.Timestamp(end))
    return [d.date() for d in sched.index]


def last_n_sessions(n: int, end: date | None = None) -> list[date]:
    """Return the last n trading sessions <= end (defaults to today ET)."""
    end = end or datetime.now(ET).date()
    # look back generously; 2x ensures enough trading days even across holidays
    start = end - timedelta(days=max(n * 2, 14))
    days = rth_sessions(start, end)
    return days[-n:]


# ---------- Fetch -----------------------------------------------------------
def _cache_path(d: date) -> Path:
    return GEX_CACHE / f"{d.isoformat()}.parquet"


def _missing_path(d: date) -> Path:
    return GEX_CACHE / f"{d.isoformat()}.missing"


def fetch_day(
    d: date,
    api_key: str,
    force: bool = False,
    session: requests.Session | None = None,
) -> Path | None:
    """Download one day of GEXbot orderflow and cache as parquet.

    Returns the parquet path on success, or None if the day has no data
    (weekend, holiday, or API 404). Marks empty days with a .missing sentinel
    so we don't hammer the API.
    """
    cache = _cache_path(d)
    miss = _missing_path(d)
    if cache.exists() and not force:
        return cache
    if miss.exists() and not force:
        return None

    sess = session or requests.Session()
    url = GEXBOT_URL.format(date=f"{d.year}-{d.month}-{d.day}")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
        "User-Agent": USER_AGENT,
    }
    r = sess.get(url, headers=headers, timeout=30)
    if r.status_code != 200:
        print("url", url)
        print("Error fetching GEXbot data:", r.status_code, r.text)
    if r.status_code == 404:
        miss.touch()
        return None
    r.raise_for_status()
    payload = r.json()
    if "url" not in payload:
        miss.touch()
        return None

    blob = sess.get(payload["url"], timeout=60)
    blob.raise_for_status()
    raw = blob.content
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    df = pd.read_json(io.BytesIO(raw))
    if df.empty:
        miss.touch()
        return None

    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="s", utc=True).dt.tz_convert(ET)
    df = df.sort_values("timestamp").drop_duplicates("timestamp").reset_index(drop=True)
    df.to_parquet(cache, index=False)
    return cache


def fetch_range(
    start: date,
    end: date,
    api_key: str,
    sleep_s: float = 0.15,
    force: bool = False,
) -> dict[date, Path | None]:
    """Fetch every RTH trading day in [start, end]. Skips cached days."""
    sess = requests.Session()
    days = rth_sessions(start, end)
    results: dict[date, Path | None] = {}

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold cyan]GEXbot"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        TextColumn("[dim]{task.description}"),
        TimeElapsedColumn(),
        console=console,
    ) as pbar:
        task = pbar.add_task("", total=len(days))
        for d in days:
            pbar.update(task, description=d.isoformat())
            try:
                results[d] = fetch_day(d, api_key, force=force, session=sess)
            except requests.HTTPError as e:
                console.print(f"[yellow]  {d} HTTP {e.response.status_code}, skipping[/]")
                results[d] = None
            except Exception as e:  # noqa: BLE001
                console.print(f"[red]  {d} error: {e!r}[/]")
                results[d] = None
            pbar.advance(task)
            time.sleep(sleep_s)

    hit = sum(1 for v in results.values() if v is not None)
    console.print(f"[green]GEXbot: {hit}/{len(days)} days available[/]")
    return results


# ---------- Load ------------------------------------------------------------
def load_day(d: date) -> pd.DataFrame | None:
    p = _cache_path(d)
    if not p.exists():
        return None
    df = pd.read_parquet(p)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True).dt.tz_convert(ET)
    return df.set_index("timestamp").sort_index()


def load_range(days: Iterable[date]) -> pd.DataFrame:
    frames = []
    for d in days:
        df = load_day(d)
        if df is not None and not df.empty:
            frames.append(df)
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, axis=0)
    return out[~out.index.duplicated(keep="first")].sort_index()


# ---------- Resample --------------------------------------------------------
def resample(df: pd.DataFrame, freq: str = "1min") -> pd.DataFrame:
    """Aggregate 1s GEX data to `freq` bars, preserving flow-burst stats.

    - Level and state columns: last observation in the bar.
    - Flow columns: sum over the bar, plus max / min for burst detection.
    - Adds a boolean `on_session_edge` flag for first/last 15m of RTH.
    """
    if df.empty:
        return df

    keep_level = [c for c in LEVEL_COLS + STATE_COLS if c in df.columns]
    keep_flow = [c for c in FLOW_COLS if c in df.columns]

    g = df.resample(freq, label="right", closed="right")
    agg_level = g[keep_level].last()
    agg_flow_sum = g[keep_flow].sum().add_suffix("_sum")
    agg_flow_max = g[keep_flow].max().add_suffix("_max")
    agg_flow_min = g[keep_flow].min().add_suffix("_min")

    out = pd.concat([agg_level, agg_flow_sum, agg_flow_max, agg_flow_min], axis=1)
    out = out.dropna(subset=["spot"])

    t = out.index
    mins = t.hour * 60 + t.minute
    out["on_session_edge"] = ((mins >= 9 * 60 + 30) & (mins < 9 * 60 + 45)) | (
        (mins >= 15 * 60 + 45) & (mins <= 16 * 60)
    )
    return out
