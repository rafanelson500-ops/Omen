"""Data daemon — keeps the local caches warm so the dashboard, backtester, and
strategy runner NEVER need a warmup period.

Two independent loops run forever:

1. **GEX 1Hz current-state poller**
   Every ``DAEMON_GEX_POLL_S`` seconds (default 1s) GETs the GEXbot live
   orderflow snapshot endpoint and appends the single returned record to
   an in-memory batch. Every ``DAEMON_GEX_FLUSH_S`` seconds (default 10s)
   the batch is merged (dedupe on ``timestamp``, keep=last) into
   ``data/gex/<day>.parquet`` -- the same path and schema that
   ``cheese.gex.fetch_day`` writes for historical backfills, so downstream
   readers (strategy runner, backtester, dashboard) are agnostic about
   whether today's file is being built live or was downloaded end-of-day.

   We poll the live current-state endpoint (not ``/v2/hist/.../{date}``)
   because the historical archive is only published at session close,
   which is useless for intraday features.

2. **Databento Live ES 1s subscriber**
   Streams ``ohlcv-1s`` for ES.c.0 continuous and batches writes every
   ``DAEMON_ES_FLUSH_S`` seconds (default 10s) to
   ``data/market_live/<day>.parquet``. Reconnects on disconnect with
   backoff.

Both loops prune files older than ``DAEMON_RETENTION_DAYS`` (default 5, which
is 3-5x the longest feature lookback). Parquet writes are atomic so concurrent
readers never see a half-written file.

Run under screen / tmux / systemd -- it has no interactive input:

    screen -dmS cheesed python scripts/data_daemon.py
    screen -r cheesed                   # attach to see the log stream
    screen -XS cheesed quit             # stop cleanly (SIGTERM)

Environment (reads from .env via python-dotenv):
    GEXBOT_API_KEY           (required for GEX loop)
    DATABENTO_API_KEY        (required for ES loop)
    DAEMON_GEX_POLL_S        (default 1)
    DAEMON_GEX_FLUSH_S       (default 10)
    DAEMON_ES_FLUSH_S        (default 10)
    DAEMON_RETENTION_DAYS    (default 5)
"""
from __future__ import annotations

import asyncio
import os
import signal
import sys
import time
from pathlib import Path

import databento as db
import httpx
import pandas as pd
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cheese.config import DATABENTO_DATASET, ES_CONTINUOUS_SYMBOL, ET, GEX_CACHE  # noqa: E402
from live import cache, logger  # noqa: E402

log = logger.get("daemon")


def _int_env(name: str, default: int) -> int:
    v = os.getenv(name)
    if not v:
        return default
    try:
        return int(v)
    except ValueError:
        return default


GEX_POLL_INTERVAL_S = _int_env("DAEMON_GEX_POLL_S", 1)
GEX_FLUSH_INTERVAL_S = _int_env("DAEMON_GEX_FLUSH_S", 10)
ES_FLUSH_INTERVAL_S = _int_env("DAEMON_ES_FLUSH_S", 10)
RETENTION_DAYS = _int_env("DAEMON_RETENTION_DAYS", 120)

GEXBOT_LIVE_URL = "https://api.gexbot.com/ES_SPX/orderflow/orderflow"
GEXBOT_USER_AGENT = "cheese-trading-daemon/1.0"


# --------------------------------------------------------------------------
# GEX 1Hz current-state poller + batched parquet flush
# --------------------------------------------------------------------------
async def _gex_periodic_flush(batch: list[dict], stop: asyncio.Event) -> None:
    """Flush `batch` to the GEX cache every GEX_FLUSH_INTERVAL_S (or on stop)."""
    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), timeout=GEX_FLUSH_INTERVAL_S)
            break
        except asyncio.TimeoutError:
            pass
        if batch:
            rows = batch[:]
            batch.clear()
            try:
                written = cache.append_gex_live(rows)
                log.info(f"gex flushed +{len(rows)} rows (file total={written:,})")
            except Exception as e:  # noqa: BLE001
                log.error(f"gex flush failed: {e!r}")


async def gex_loop(api_key: str, stop: asyncio.Event) -> None:
    log.info(
        f"gex poller: poll={GEX_POLL_INTERVAL_S}s flush={GEX_FLUSH_INTERVAL_S}s "
        f"retain={RETENTION_DAYS}d url={GEXBOT_LIVE_URL}"
    )
    batch: list[dict] = []
    flush_task = asyncio.create_task(_gex_periodic_flush(batch, stop))
    last_ts: int | None = None
    last_prune = 0.0
    auth_backoff_s = 30.0
    # GEXbot rejects requests that present both Authorization header and
    # ?key=<KEY> query param ("Multiple API keys detected"). Use the header
    # alone -- it's accepted on both api.gex.bot/v2 and api.gexbot.com.
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
        "User-Agent": GEXBOT_USER_AGENT,
    }

    try:
        async with httpx.AsyncClient(timeout=10.0, headers=headers) as client:
            while not stop.is_set():
                t0 = time.monotonic()
                try:
                    r = await client.get(GEXBOT_LIVE_URL)
                    if r.status_code == 200:
                        rec = r.json()
                        # Endpoint returns a single JSON object per call. The
                        # server may repeat the same tick between publishes --
                        # drop consecutive identical timestamps at ingest to
                        # keep the batch (and the per-flush dedupe work) small.
                        ts = rec.get("timestamp") if isinstance(rec, dict) else None
                        if isinstance(ts, (int, float)) and rec.get("ticker"):
                            ts_int = int(ts)
                            if ts_int != last_ts:
                                batch.append(rec)
                                last_ts = ts_int
                    elif r.status_code in (401, 403):
                        log.error(
                            f"gex auth error {r.status_code}: {r.text[:200]}; "
                            f"backing off {auth_backoff_s:.0f}s"
                        )
                        try:
                            await asyncio.wait_for(stop.wait(), timeout=auth_backoff_s)
                            break
                        except asyncio.TimeoutError:
                            continue
                    elif r.status_code == 404:
                        # Pre-market / weekend / holiday — endpoint returns 404
                        # until the feed is populated. Don't log per-tick.
                        pass
                    else:
                        log.warning(f"gex HTTP {r.status_code}: {r.text[:160]}")
                except httpx.HTTPError as e:
                    log.warning(f"gex poll failed: {e!r}")
                except Exception as e:  # noqa: BLE001
                    log.warning(f"gex poll unexpected: {e!r}")

                if time.monotonic() - last_prune > 3600:
                    removed = cache.prune_stale(GEX_CACHE, RETENTION_DAYS)
                    if removed:
                        log.info(f"gex pruned {removed} old file(s)")
                    last_prune = time.monotonic()

                elapsed = time.monotonic() - t0
                delay = max(0.05, GEX_POLL_INTERVAL_S - elapsed)
                try:
                    await asyncio.wait_for(stop.wait(), timeout=delay)
                    break
                except asyncio.TimeoutError:
                    continue
    finally:
        flush_task.cancel()
        try:
            await flush_task
        except asyncio.CancelledError:
            pass
        if batch:
            try:
                cache.append_gex_live(batch)
            except Exception:  # noqa: BLE001
                pass


# --------------------------------------------------------------------------
# Databento Live 1s subscriber with batched disk flushes
# --------------------------------------------------------------------------
async def _periodic_flush(batch: list[dict], stop: asyncio.Event) -> None:
    """Flush `batch` to parquet every ES_FLUSH_INTERVAL_S (or on stop)."""
    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), timeout=ES_FLUSH_INTERVAL_S)
            break
        except asyncio.TimeoutError:
            pass
        if batch:
            rows = batch[:]
            batch.clear()
            try:
                written = cache.append_market_live(rows)
                log.info(f"market_live flushed +{len(rows)} rows (file total={written:,})")
            except Exception as e:  # noqa: BLE001
                log.error(f"market_live flush failed: {e!r}")


async def es_loop(api_key: str, stop: asyncio.Event) -> None:
    log.info(f"es streamer: flush={ES_FLUSH_INTERVAL_S}s retain={RETENTION_DAYS}d")
    backoff = 5.0
    while not stop.is_set():
        batch: list[dict] = []
        client: db.Live | None = None
        flush_task: asyncio.Task | None = None
        last_prune = 0.0
        try:
            client = db.Live(key=api_key)
            client.subscribe(
                dataset=DATABENTO_DATASET,
                schema="ohlcv-1s",
                stype_in="continuous",
                symbols=[ES_CONTINUOUS_SYMBOL],
            )
            log.info(f"databento live subscribed {ES_CONTINUOUS_SYMBOL} ohlcv-1s")
            flush_task = asyncio.create_task(_periodic_flush(batch, stop))
            backoff = 5.0  # reset after a successful connect

            async for rec in client:  # type: ignore[attr-defined]
                if stop.is_set():
                    break
                # Databento prefaces the session with SystemMsg / SymbolMappingMsg
                # etc. Those have ts_event but no OHLCV fields -- guard the whole
                # block so only OHLCVMsg-shaped records are ingested.
                try:
                    ts_ns = int(rec.ts_event)
                    scale = 1e-9
                    o = rec.open * scale
                    h = rec.high * scale
                    l = rec.low * scale
                    c = rec.close * scale
                    v = int(rec.volume)
                except AttributeError:
                    continue
                ts = pd.Timestamp(ts_ns, unit="ns", tz="UTC").tz_convert(ET)
                batch.append({
                    "ts": ts,
                    "open": o, "high": h, "low": l, "close": c, "volume": v,
                })
                # Prune at most once per hour to avoid disk churn.
                if time.monotonic() - last_prune > 3600:
                    removed = cache.prune_stale(cache.MARKET_LIVE_CACHE, RETENTION_DAYS)
                    if removed:
                        log.info(f"market_live pruned {removed} old file(s)")
                    last_prune = time.monotonic()
        except Exception as e:  # noqa: BLE001
            log.error(f"databento live stream error: {e!r}")
        finally:
            if flush_task is not None:
                flush_task.cancel()
                try:
                    await flush_task
                except asyncio.CancelledError:
                    pass
            # Flush whatever is left in the batch before exit/reconnect.
            if batch:
                try:
                    cache.append_market_live(batch)
                except Exception:  # noqa: BLE001
                    pass
            if client is not None:
                try:
                    client.stop()
                except Exception:  # noqa: BLE001
                    pass

        if stop.is_set():
            return
        # Exponential backoff, capped at 60s, between reconnect attempts.
        log.warning(f"es streamer disconnected; reconnecting in {backoff:.0f}s")
        try:
            await asyncio.wait_for(stop.wait(), timeout=backoff)
            return
        except asyncio.TimeoutError:
            backoff = min(60.0, backoff * 1.5)


# --------------------------------------------------------------------------
# Entrypoint
# --------------------------------------------------------------------------
async def main() -> None:
    load_dotenv()
    logger.setup()

    gex_key = os.getenv("GEXBOT_API_KEY", "")
    dbn_key = os.getenv("DATABENTO_API_KEY", "")
    if not gex_key:
        log.warning("GEXBOT_API_KEY missing; GEX loop disabled")
    if not dbn_key:
        log.warning("DATABENTO_API_KEY missing; ES loop disabled")
    if not (gex_key or dbn_key):
        log.error("no API keys present; exiting")
        return

    stop = asyncio.Event()

    def _sig(*_a):
        log.warning("daemon shutdown signal received")
        stop.set()

    loop = asyncio.get_running_loop()
    for sig_name in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig_name, _sig)
        except NotImplementedError:
            pass  # windows

    tasks: list[asyncio.Task] = []
    if gex_key:
        tasks.append(asyncio.create_task(gex_loop(gex_key, stop), name="gex_loop"))
    if dbn_key:
        tasks.append(asyncio.create_task(es_loop(dbn_key, stop), name="es_loop"))

    log.info(f"daemon up ({len(tasks)} task(s)); SIGINT/SIGTERM to stop")
    try:
        await stop.wait()
    finally:
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        log.info("daemon stopped")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
