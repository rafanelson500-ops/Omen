"""Bus-piped logger. Every record is also pushed to the frontend in realtime."""
from __future__ import annotations

import logging
import sys
from typing import Any

from rich.console import Console
from rich.logging import RichHandler

from live.bus import BUS

_console = Console(stderr=True)


class _BusHandler(logging.Handler):
    """Mirror every log record onto the EventBus 'log' channel."""

    def emit(self, record: logging.LogRecord) -> None:  # noqa: D401
        try:
            msg = record.getMessage()
            extra = {
                k: v for k, v in record.__dict__.items()
                if k not in _LOGRECORD_BUILTIN and not k.startswith("_")
            }
            BUS.publish_nowait("log", {
                "level": record.levelname,
                "source": record.name,
                "msg": msg,
                "extra": extra or None,
            })
        except Exception:  # noqa: BLE001
            pass


_LOGRECORD_BUILTIN = {
    "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
    "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
    "created", "msecs", "relativeCreated", "thread", "threadName",
    "processName", "process", "message", "asctime",
}

_configured = False


def setup(level: int = logging.INFO) -> None:
    """Configure root logger once: Rich console + bus mirror."""
    global _configured
    if _configured:
        return
    root = logging.getLogger()
    root.setLevel(level)
    for h in list(root.handlers):
        root.removeHandler(h)
    rich_handler = RichHandler(console=_console, show_path=False, rich_tracebacks=True,
                               markup=False, log_time_format="%H:%M:%S")
    root.addHandler(rich_handler)
    root.addHandler(_BusHandler())

    # Quiet noisy libs
    for noisy in ("asyncio", "websockets.client", "websockets.server",
                  "httpx", "httpcore", "urllib3", "databento"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    _configured = True


def get(name: str) -> logging.Logger:
    setup()
    return logging.getLogger(name)
