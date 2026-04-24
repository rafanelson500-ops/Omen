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
import os
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

# Shutdown budget before we hard-kill the process. Needed because third-party
# libs (databento, azure webpubsub) sometimes hold background threads that
# refuse to honour cancellation.
SHUTDOWN_GRACE_S = 8.0


async def supervised(name: str, coro_factory, *, stop: asyncio.Event,
                     restart_delay: float = 5.0) -> None:
    """Restart a coroutine if it exits, with backoff.

    Stops restarting once `stop` is set so Ctrl-C doesn't race a restart.
    """
    while not stop.is_set():
        try:
            await coro_factory()
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            log.error(f"{name} crashed: {e!r}; restarting in {restart_delay}s")
            await BUS.publish("status", {"component": name, "ok": False, "error": repr(e)})
        else:
            if stop.is_set():
                return
            log.warning(f"{name} exited cleanly; restarting in {restart_delay}s")
            await BUS.publish("status", {"component": name, "ok": False, "exited": True})
        # Sleep with early-exit when shutdown fires mid-backoff.
        try:
            await asyncio.wait_for(stop.wait(), timeout=restart_delay)
            return
        except asyncio.TimeoutError:
            continue


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
    # The strategy runner is ALWAYS on; GEXbot WS + Databento Live are
    # optional tile feeds gated by env flags. The strategy itself reads
    # from the on-disk cache populated by scripts/data_daemon.py, so it
    # works correctly even when both are disabled.
    gex_hub: GEXbotHub | None = None
    dbn = DatabentoOHLCV(api_key=s.databento_api_key) if s.databento_enabled else None

    async def _gex_flow():
        nonlocal gex_hub
        # A fresh GEXbotHub is needed after each disconnect (Azure SDK one-shot).
        gex_hub = GEXbotHub(api_key=s.gexbot_api_key, hub="orderflow",
                            ticker="ES_SPX")
        await gex_hub.run()

    async def _dbn_flow():
        assert dbn is not None
        await dbn.run()

    async def _strat_flow():
        await runner.run()

    async def _account_flow():
        await tv.account_poll_loop(interval=10.0)

    stop = asyncio.Event()

    tasks: list[asyncio.Task] = [
        asyncio.create_task(supervised("strategy", _strat_flow, stop=stop)),
        asyncio.create_task(supervised("tradovate_account", _account_flow,
                                       stop=stop, restart_delay=10.0)),
    ]
    if s.gexbot_ws_enabled:
        log.info("gexbot_ws ENABLED (LIVE_GEXBOT_WS_ENABLED=1)")
        tasks.append(asyncio.create_task(supervised("gexbot", _gex_flow, stop=stop)))
    else:
        log.info("gexbot_ws disabled; strategy uses REST-fed cache via data_daemon.py")
    if s.databento_enabled:
        log.info("databento_live ENABLED (LIVE_DATABENTO_ENABLED=1)")
        tasks.append(asyncio.create_task(supervised("databento_live", _dbn_flow, stop=stop)))
    else:
        log.info("databento_live disabled; strategy uses daemon-fed cache")

    # --- FastAPI server
    app = build_app(runner=runner, tradovate=tv)
    config = uvicorn.Config(app, host=s.host, port=s.port, log_level="warning",
                            access_log=False, lifespan="off")
    server = uvicorn.Server(config)
    log.info(f"dashboard http://{s.host}:{s.port}")

    # Track how many shutdown signals we've received. First Ctrl-C runs the
    # graceful path; a second press (or any signal after the grace window)
    # escalates to os._exit() because some third-party libs hold threads
    # that refuse to honour cancellation.
    sig_count = {"n": 0}

    def _sig(*_a):
        sig_count["n"] += 1
        if sig_count["n"] == 1:
            log.warning("shutdown signal received (Ctrl-C again to force-exit)")
            stop.set()
        else:
            log.warning(f"force-exit on signal #{sig_count['n']}")
            os._exit(130)

    loop = asyncio.get_running_loop()
    for sig_name in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig_name, _sig)
        except NotImplementedError:
            pass  # windows

    server_task = asyncio.create_task(server.serve())

    async def _graceful_shutdown() -> None:
        log.info("shutting down ...")
        server.should_exit = True
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        if gex_hub is not None:
            await gex_hub.close()
        if dbn is not None:
            await dbn.close()
        await tv.close()
        server_task.cancel()
        try:
            await server_task
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass

    try:
        await stop.wait()
    finally:
        try:
            await asyncio.wait_for(_graceful_shutdown(), timeout=SHUTDOWN_GRACE_S)
        except asyncio.TimeoutError:
            log.warning(f"graceful shutdown timed out after {SHUTDOWN_GRACE_S:.0f}s; "
                        "force-exiting")
            os._exit(130)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
