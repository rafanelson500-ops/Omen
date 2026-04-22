"""In-process event bus and ring-buffered log + state.

Everything in the live stack publishes events onto a single bus. The FastAPI
dashboard, the strategy runner, and anything else just subscribe.

Event envelope:
    {
        "t":  ISO-8601 timestamp,
        "ch": channel name ("log" | "price" | "flow" | "signal" | "order" | "status"),
        "data": payload dict,
    }

Channels:
    log     - structured log records ({level, source, msg, extra?})
    price   - realtime ES price update ({ts, symbol, price, ohlc})
    flow    - realtime GEXbot orderflow payload
    signal  - strategy signal fired ({ts, side, z, features})
    order   - order lifecycle (submit, ack, fill, reject)
    status  - connection health heartbeat per component
"""
from __future__ import annotations

import asyncio
import json
import time
from collections import deque
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, AsyncIterator


@dataclass
class Event:
    t: str
    ch: str
    data: dict[str, Any]

    def to_json(self) -> str:
        return json.dumps(asdict(self), default=str)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class EventBus:
    """Simple async fan-out bus with a bounded ring buffer of recent events."""

    def __init__(self, history: int = 2000) -> None:
        self._subscribers: list[asyncio.Queue[Event]] = []
        self._lock = asyncio.Lock()
        self._history: deque[Event] = deque(maxlen=history)
        # "status" is a dict of {component: last_event_dict}
        self.status: dict[str, dict[str, Any]] = {}
        # Captured by the async app once the event loop is running; used by
        # publish_threadsafe() so non-async threads can publish safely.
        self._loop: asyncio.AbstractEventLoop | None = None

    def attach_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def publish_threadsafe(self, channel: str, data: dict[str, Any]) -> None:
        """Publish from a non-asyncio thread. Safe to call before attach_loop;
        if no loop is attached yet, falls back to publish_nowait (which mutates
        the ring buffer but may drop subscriber deliveries)."""
        loop = self._loop
        if loop is None or not loop.is_running():
            self.publish_nowait(channel, data)
            return
        loop.call_soon_threadsafe(self.publish_nowait, channel, data)

    async def publish(self, channel: str, data: dict[str, Any]) -> None:
        ev = Event(t=_now_iso(), ch=channel, data=data)
        self._history.append(ev)
        if channel == "status":
            self.status[data.get("component", "?")] = data
        async with self._lock:
            dead: list[asyncio.Queue[Event]] = []
            for q in self._subscribers:
                try:
                    q.put_nowait(ev)
                except asyncio.QueueFull:
                    dead.append(q)
            for q in dead:
                self._subscribers.remove(q)

    def publish_nowait(self, channel: str, data: dict[str, Any]) -> None:
        """Sync publish used from non-async contexts (e.g. log handlers)."""
        ev = Event(t=_now_iso(), ch=channel, data=data)
        self._history.append(ev)
        if channel == "status":
            self.status[data.get("component", "?")] = data
        for q in list(self._subscribers):
            try:
                q.put_nowait(ev)
            except asyncio.QueueFull:
                pass

    async def subscribe(self, queue_size: int = 1024) -> asyncio.Queue[Event]:
        q: asyncio.Queue[Event] = asyncio.Queue(maxsize=queue_size)
        for ev in list(self._history):
            try:
                q.put_nowait(ev)
            except asyncio.QueueFull:
                break
        async with self._lock:
            self._subscribers.append(q)
        return q

    async def unsubscribe(self, queue: asyncio.Queue[Event]) -> None:
        async with self._lock:
            if queue in self._subscribers:
                self._subscribers.remove(queue)

    async def stream(self) -> AsyncIterator[Event]:
        q = await self.subscribe()
        try:
            while True:
                ev = await q.get()
                yield ev
        finally:
            await self.unsubscribe(q)

    def history_snapshot(self) -> list[dict[str, Any]]:
        return [asdict(ev) for ev in list(self._history)]


# Global singleton for convenience
BUS = EventBus()
