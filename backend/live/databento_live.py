"""Databento Live subscription: ohlcv-1s for ES continuous front month.

Emits price updates onto the bus on the 'price' channel with shape:
    {src: 'databento', ts: iso, symbol: str, open, high, low, close, volume}
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import databento as db

from live.bus import BUS
from live.logger import get

log = get("databento_live")


class DatabentoOHLCV:
    def __init__(self, api_key: str, dataset: str = "GLBX.MDP3",
                 symbol: str = "ES.c.0", schema: str = "ohlcv-1s") -> None:
        self.api_key = api_key
        self.dataset = dataset
        self.symbol = symbol
        self.schema = schema
        self._client: db.Live | None = None
        self._shutdown = asyncio.Event()

    async def run(self) -> None:
        loop = asyncio.get_running_loop()
        self._client = db.Live(key=self.api_key)
        # databento.Live.subscribe is synchronous and blocking on setup; run in a thread
        log.info(f"databento live subscribe {self.symbol} {self.schema} {self.dataset}")
        await loop.run_in_executor(None, self._subscribe_sync)
        try:
            async for record in self._client:  # type: ignore[attr-defined]
                await self._on_record(record)
        except Exception as e:  # noqa: BLE001
            log.error(f"databento live stream error: {e!r}")
        finally:
            await BUS.publish("status", {"component": "databento_live", "ok": False})
            log.warning("databento live stream ended")

    def _subscribe_sync(self) -> None:
        """Subscribe only. Do NOT call client.start() here: the async iterator
        in run() drives the session itself, and calling start() before iterating
        raises 'Cannot start iteration after streaming has started'."""
        assert self._client is not None
        self._client.subscribe(
            dataset=self.dataset,
            schema=self.schema,
            stype_in="continuous",
            symbols=[self.symbol],
        )
        log.info("databento live subscribed")

    async def _on_record(self, record) -> None:  # noqa: ANN001
        # ohlcv-1s records expose ts_event (nanos), open/high/low/close/volume as int (scaled by 1e9)
        # Databento convention: prices are stored as int64 * 1e-9
        try:
            ts_ns = int(record.ts_event)
            ts = datetime.fromtimestamp(ts_ns / 1e9, tz=timezone.utc).isoformat(timespec="milliseconds")
            scale = 1e-9
            o = record.open * scale
            h = record.high * scale
            l = record.low * scale
            c = record.close * scale
            v = int(record.volume)
        except AttributeError:
            return
        await BUS.publish("price", {
            "src": "databento", "ts": ts, "symbol": self.symbol,
            "open": o, "high": h, "low": l, "close": c, "volume": v,
        })
        await BUS.publish("status", {"component": "databento_live", "ok": True, "last_ts": ts})

    async def close(self) -> None:
        self._shutdown.set()
        if self._client is not None:
            try:
                self._client.stop()
            except Exception:  # noqa: BLE001
                pass
