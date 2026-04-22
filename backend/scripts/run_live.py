"""Live trading entrypoint.

Starts:
    - FastAPI dashboard (http://HOST:PORT)
    - Tradovate auth + token-refresh loop + trading WS + market-data WS
    - Databento Live ohlcv-1s ES.c.0 stream
    - GEXbot realtime orderflow hub
    - Strategy runner (flow_burst -> bracket OSO orders)

Safe by default: dry_run=True until you click ARM in the UI or set
LIVE_DRY_RUN=0 in .env.

Usage:
    python scripts/run_live.py
"""
from __future__ import annotations

import asyncio
import signal
import sys
from pathlib import Path

import uvicorn
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from live import logger, settings as settings_mod
from live.app import build_app
from live.bus import BUS
from live.databento_live import DatabentoOHLCV
from live.gexbot_ws import GEXbotHub
from live.strategy_live import StrategyRunner
from live.tradovate import TradovateClient

log = logger.get("main")


async def supervised(name: str, coro_factory, *, restart_delay: float = 5.0) -> None:
    """Restart a coroutine if it exits, with backoff."""
    while True:
        try:
            await coro_factory()
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            log.error(f"{name} crashed: {e!r}; restarting in {restart_delay}s")
            await BUS.publish("status", {"component": name, "ok": False, "error": repr(e)})
        else:
            log.warning(f"{name} exited cleanly; restarting in {restart_delay}s")
            await BUS.publish("status", {"component": name, "ok": False, "exited": True})
        await asyncio.sleep(restart_delay)


async def main() -> None:
    load_dotenv()
    logger.setup()
    s = settings_mod.load()
    BUS.attach_loop(asyncio.get_running_loop())

    log.info(f"env={s.env} dry_run={s.dry_run} bar_freq={s.bar_freq} "
             f"z={s.z_threshold} stop={s.stop_atr_mult} tgt={s.target_atr_mult} "
             f"time_stop_min={s.time_stop_min}")

    # --- Tradovate up first (we need contract + account for strategy)
    tv = TradovateClient(s)
    contract = await tv.bootstrap()
    await tv.connect_trading_ws()
    await tv.connect_md_ws()
    await tv.subscribe_quote(contract["name"])

    # --- Strategy runner
    runner = StrategyRunner(s, tv, contract)

    # --- Background streams (supervised, auto-restart)
    gex_hub = GEXbotHub(api_key=s.gexbot_api_key, hub="orderflow",
                        ticker="ES_SPX")
    dbn = DatabentoOHLCV(api_key=s.databento_api_key)

    async def _gex_flow():
        # A fresh GEXbotHub is needed after each disconnect (Azure SDK one-shot).
        nonlocal gex_hub
        gex_hub = GEXbotHub(api_key=s.gexbot_api_key, hub="orderflow",
                            ticker="ES_SPX")
        await gex_hub.run()

    async def _dbn_flow():
        await dbn.run()

    async def _strat_flow():
        await runner.run()

    tasks = [
        asyncio.create_task(supervised("gexbot", _gex_flow)),
        asyncio.create_task(supervised("databento_live", _dbn_flow)),
        asyncio.create_task(supervised("strategy", _strat_flow)),
    ]

    # --- FastAPI server
    app = build_app(runner=runner)
    config = uvicorn.Config(app, host=s.host, port=s.port, log_level="warning",
                            access_log=False, lifespan="off")
    server = uvicorn.Server(config)
    log.info(f"dashboard http://{s.host}:{s.port}")

    stop = asyncio.Event()

    def _sig(*_a):
        log.warning("shutdown signal received")
        stop.set()

    loop = asyncio.get_running_loop()
    for sig_name in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig_name, _sig)
        except NotImplementedError:
            pass  # windows

    server_task = asyncio.create_task(server.serve())

    try:
        await stop.wait()
    finally:
        log.info("shutting down ...")
        server.should_exit = True
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await gex_hub.close()
        await dbn.close()
        await tv.close()
        await server_task


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
