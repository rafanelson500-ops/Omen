"""FastAPI live dashboard: static SPA + WebSocket fan-out of bus events."""
from __future__ import annotations

import asyncio
import time as _time
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from live.bus import BUS
from live.logger import get

log = get("app")

STATIC_DIR = Path(__file__).parent / "static"
_CACHE_BUST = str(int(_time.time()))


def build_app(runner=None) -> FastAPI:
    app = FastAPI(title="Cheese Live")

    @app.get("/", response_class=HTMLResponse)
    async def index() -> HTMLResponse:
        html = (STATIC_DIR / "index.html").read_text()
        # Dev cache-buster: appended once per server boot so browsers always
        # load the latest app.js / styles.css after a backend restart.
        html = html.replace("/static/styles.css", f"/static/styles.css?v={_CACHE_BUST}")
        html = html.replace("/static/app.js",     f"/static/app.js?v={_CACHE_BUST}")
        return HTMLResponse(html)

    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/api/status")
    async def api_status() -> JSONResponse:
        return JSONResponse({
            "components": BUS.status,
            "armed": bool(runner.armed) if runner else False,
        })

    @app.post("/api/arm")
    async def api_arm(flag: bool = True) -> JSONResponse:
        if runner is None:
            return JSONResponse({"error": "no runner"}, status_code=503)
        runner.set_armed(flag)
        return JSONResponse({"armed": runner.armed})

    @app.get("/api/history")
    async def api_history() -> JSONResponse:
        return JSONResponse(BUS.history_snapshot())

    @app.websocket("/ws")
    async def ws(sock: WebSocket) -> None:
        await sock.accept()
        q = await BUS.subscribe(queue_size=4096)
        try:
            # Ship the entire history ring as a single batch frame so the client
            # can process + render once instead of re-rendering the log DOM for
            # every individual event. With a full 2000-event backlog the old
            # per-event path was triggering thousands of innerHTML rebuilds.
            hist = BUS.history_snapshot()
            if hist:
                await sock.send_json({
                    "ch": "__hydrate__",
                    "t": hist[-1]["t"],
                    "events": hist,
                })
            while True:
                ev = await q.get()
                await sock.send_text(ev.to_json())
        except WebSocketDisconnect:
            pass
        except Exception as e:  # noqa: BLE001
            log.warning(f"client ws error: {e!r}")
        finally:
            await BUS.unsubscribe(q)

    return app
