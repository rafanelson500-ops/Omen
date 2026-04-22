"""Shared live cache — rolling per-day parquet files on disk.

Purpose
-------
Eliminate the "warmup" period for the live strategy and dashboard. A separate
daemon (``scripts/data_daemon.py``) continuously writes:

    data/gex/{YYYY-MM-DD}.parquet          -- GEXbot REST orderflow (existing)
    data/market_live/{YYYY-MM-DD}.parquet  -- Databento Live 1s ES OHLCV (new)

Readers (``StrategyRunner``, Streamlit backtester) load the most recent N days
on demand. The daemon runs independently under ``screen`` / ``systemd`` so the
cache stays warm even when the dashboard process is off.

Design notes
------------
* Day-partitioned so retention pruning is a simple ``os.remove`` per date and
  concurrent readers never see a half-written file.
* Writes are atomic: parquet is written to a sibling tmp file then
  ``os.replace()``'d into place (POSIX atomic rename).
* Timestamps are stored naive-UTC in parquet and re-localized to ET on load;
  this matches how ``cheese.gex`` already handles per-day files.
"""
from __future__ import annotations

import os
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

from cheese.config import DATA_DIR, ET

MARKET_LIVE_CACHE = DATA_DIR / "market_live"
MARKET_LIVE_CACHE.mkdir(parents=True, exist_ok=True)


# ---------- Atomic parquet write --------------------------------------------
def atomic_write_parquet(df: pd.DataFrame, path: Path) -> None:
    """Write `df` to `path` atomically via write-to-tmp + rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp_", suffix=".parquet", dir=str(path.parent))
    os.close(fd)
    tmp_path = Path(tmp)
    try:
        df.to_parquet(tmp_path, index=True)
        os.replace(tmp_path, path)
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass


# ---------- Market live 1s cache --------------------------------------------
def market_live_path(d: date) -> Path:
    return MARKET_LIVE_CACHE / f"{d.isoformat()}.parquet"


def append_market_live(rows: list[dict]) -> int:
    """Merge a batch of 1s OHLCV rows into per-day cache files.

    Each row: ``{"ts": <ET-aware Timestamp>, "open", "high", "low", "close", "volume"}``.
    Returns the total rows written across all affected days (post-dedupe).
    """
    if not rows:
        return 0

    by_day: dict[date, list[dict]] = {}
    for r in rows:
        ts: pd.Timestamp = r["ts"]
        by_day.setdefault(ts.date(), []).append(r)

    total = 0
    for d, batch in by_day.items():
        path = market_live_path(d)
        new = pd.DataFrame(batch).set_index("ts").sort_index()
        new = new[~new.index.duplicated(keep="last")]
        if path.exists():
            try:
                prev = pd.read_parquet(path)
                prev.index = pd.to_datetime(prev.index, utc=True).tz_convert(ET)
                combined = pd.concat([prev, new])
                combined = combined[~combined.index.duplicated(keep="last")].sort_index()
            except Exception:
                combined = new
        else:
            combined = new
        atomic_write_parquet(combined, path)
        total += len(combined)
    return total


def load_market_live(since: pd.Timestamp | None = None) -> pd.DataFrame:
    """Load cached 1s ES data with index >= `since` (ET-aware). Empty if none."""
    if not MARKET_LIVE_CACHE.exists():
        return pd.DataFrame()
    frames: list[pd.DataFrame] = []
    for p in sorted(MARKET_LIVE_CACHE.glob("*.parquet")):
        try:
            df = pd.read_parquet(p)
            df.index = pd.to_datetime(df.index, utc=True).tz_convert(ET)
            if since is not None:
                df = df[df.index >= since]
            if not df.empty:
                frames.append(df)
        except Exception:
            continue
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames).sort_index()
    return out[~out.index.duplicated(keep="last")]


# ---------- Retention pruning -----------------------------------------------
def prune_stale(directory: Path, retain_days: int) -> int:
    """Remove ``{YYYY-MM-DD}.parquet`` files older than `retain_days` from today ET.

    Files that can't be parsed as dates are left alone. Returns count removed.
    """
    if not directory.exists():
        return 0
    cutoff = datetime.now(ET).date() - timedelta(days=retain_days)
    removed = 0
    for p in directory.glob("*.parquet"):
        try:
            d = date.fromisoformat(p.stem)
        except ValueError:
            continue
        if d < cutoff:
            try:
                p.unlink()
                removed += 1
            except OSError:
                pass
    return removed


__all__ = [
    "MARKET_LIVE_CACHE",
    "atomic_write_parquet",
    "market_live_path",
    "append_market_live",
    "load_market_live",
    "prune_stale",
]
