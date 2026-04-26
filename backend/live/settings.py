"""Environment-based configuration for the live stack.

All Tradovate + GEXbot + Databento credentials are read here from the process
environment (populated from .env by python-dotenv). Safety flags are immutable
for a given process; flip them by restarting with different env.

Required .env keys:
    DATABENTO_API_KEY        - Databento Historical + Live
    GEXBOT_API_KEY           - GEXbot REST + WS
    TRADOVATE_USERNAME       - Tradovate account username
    TRADOVATE_PASSWORD       - Tradovate API password (see Tradovate -> API access)
    TRADOVATE_APP_ID         - Tradovate App ID
    TRADOVATE_APP_VERSION    - Tradovate App version (default: "1.0")
    TRADOVATE_CID            - Client ID (integer)
    TRADOVATE_SECRET         - Client secret
    TRADOVATE_DEVICE_ID      - Any stable unique string for this machine (default: hostname)
    TRADOVATE_ACCOUNT_SPEC   - Account name (e.g. the account nickname); optional, auto-discovered if blank

Optional tuning:
    LIVE_ENV                 - "demo" (default) or "live"
    LIVE_DRY_RUN             - "1" (default) to log orders only; "0" to actually submit
    LIVE_SYMBOL_ROOT         - "ES" (default)
    LIVE_QUANTITY            - default 1 contract
    LIVE_BAR_FREQ            - "5min" (default) or "1min"
    LIVE_Z_THRESHOLD         - default 2.0
    LIVE_STOP_ATR_MULT       - default 1.0
    LIVE_TARGET_ATR_MULT     - default 6.0
    LIVE_TIME_STOP_MIN       - default 25
    LIVE_HOST                - "127.0.0.1"
    LIVE_PORT                - 8765

Data source flags (used in conjunction with scripts/data_daemon.py):
    LIVE_GEXBOT_WS_ENABLED   - "0" (default). The WS protobuf schema is
                                best-guess without the .proto file and currently
                                decodes to garbage (spot=715141 etc.). Keep OFF
                                until the schema is verified; the strategy uses
                                REST data via the daemon regardless.
    LIVE_DATABENTO_ENABLED   - "1" (default). ES 1s live WS for real-time tile
                                updates. Set "0" if the daemon is the only
                                Databento subscriber (avoids double billing).
"""
from __future__ import annotations

import os
import socket
from dataclasses import dataclass, field
from typing import Literal


@dataclass(frozen=True)
class TradovateCreds:
    name: str
    password: str
    app_id: str
    app_version: str
    cid: int
    sec: str
    device_id: str
    account_spec: str | None  # optional; auto-discovered if missing

    @property
    def is_complete(self) -> bool:
        return bool(self.name and self.password and self.app_id and self.cid and self.sec)


@dataclass(frozen=True)
class LiveSettings:
    env: Literal["demo", "live"] = "demo"
    dry_run: bool = True
    symbol_root: str = "ES"
    sizing_mode: str = "static"
    account_size: float = 100000.0
    kelly_fraction: float = 1.0
    quantity: int = 1
    bar_freq: str = "5min"
    z_threshold: float = 2.0
    stop_atr_mult: float = 1.0
    target_atr_mult: float = 6.0
    time_stop_min: int = 25
    host: str = "127.0.0.1"
    port: int = 8765
    databento_api_key: str = ""
    gexbot_api_key: str = ""
    # Data-source toggles (see module docstring)
    gexbot_ws_enabled: bool = False
    databento_enabled: bool = True
    tradovate: TradovateCreds = field(default_factory=lambda: TradovateCreds("", "", "", "1.0", 0, "", socket.gethostname(), None))

    # Computed Tradovate endpoints
    @property
    def tradovate_rest(self) -> str:
        return "https://demo.tradovateapi.com/v1" if self.env == "demo" else "https://live.tradovateapi.com/v1"

    @property
    def tradovate_rest_live(self) -> str:
        """Token renewal endpoint lives on the LIVE subdomain for both envs."""
        return "https://live.tradovateapi.com/v1"

    @property
    def tradovate_ws_trading(self) -> str:
        return "wss://demo.tradovateapi.com/v1/websocket" if self.env == "demo" else "wss://live.tradovateapi.com/v1/websocket"

    @property
    def tradovate_ws_md(self) -> str:
        return "wss://md-demo.tradovateapi.com/v1/websocket" if self.env == "demo" else "wss://md.tradovateapi.com/v1/websocket"


def _bool(v: str | None, default: bool) -> bool:
    if v is None:
        return default
    return v.strip().lower() in {"1", "true", "yes", "on", "y"}


def _int(v: str | None, default: int) -> int:
    try:
        return int(v) if v else default
    except ValueError:
        return default


def _float(v: str | None, default: float) -> float:
    try:
        return float(v) if v else default
    except ValueError:
        return default


def load() -> LiveSettings:
    """Load settings from environment. Safe to call multiple times."""
    env_val = os.getenv("LIVE_ENV", "demo").lower()
    if env_val not in ("demo", "live"):
        env_val = "demo"

    tc = TradovateCreds(
        name=os.getenv("TRADOVATE_USERNAME", ""),
        password=os.getenv("TRADOVATE_PASSWORD", ""),
        app_id=os.getenv("TRADOVATE_APP_ID", ""),
        app_version=os.getenv("TRADOVATE_APP_VERSION", "1.0"),
        cid=_int(os.getenv("TRADOVATE_CID"), 0),
        sec=os.getenv("TRADOVATE_SECRET", ""),
        device_id=os.getenv("TRADOVATE_DEVICE_ID") or socket.gethostname(),
        account_spec=os.getenv("TRADOVATE_ACCOUNT_SPEC") or None,
    )

    return LiveSettings(
        env=env_val,                           # type: ignore[arg-type]
        dry_run=_bool(os.getenv("LIVE_DRY_RUN"), True),
        symbol_root=os.getenv("LIVE_INSTRUMENT", os.getenv("LIVE_SYMBOL_ROOT", "ES")),
        sizing_mode=os.getenv("LIVE_SIZING_MODE", "static"),
        account_size=_float(os.getenv("LIVE_ACCOUNT_SIZE"), 100000.0),
        kelly_fraction=_float(os.getenv("LIVE_KELLY_FRACTION"), 1.0),
        quantity=_int(os.getenv("LIVE_QUANTITY"), 1),
        bar_freq=os.getenv("LIVE_BAR_FREQ", "5min"),
        z_threshold=_float(os.getenv("LIVE_Z_THRESHOLD"), 2.0),
        stop_atr_mult=_float(os.getenv("LIVE_STOP_ATR_MULT"), 1.0),
        target_atr_mult=_float(os.getenv("LIVE_TARGET_ATR_MULT"), 6.0),
        time_stop_min=_int(os.getenv("LIVE_TIME_STOP_MIN"), 25),
        host=os.getenv("LIVE_HOST", "127.0.0.1"),
        port=_int(os.getenv("LIVE_PORT"), 8765),
        databento_api_key=os.getenv("DATABENTO_API_KEY", ""),
        gexbot_api_key=os.getenv("GEXBOT_API_KEY", ""),
        gexbot_ws_enabled=_bool(os.getenv("LIVE_GEXBOT_WS_ENABLED"), False),
        databento_enabled=_bool(os.getenv("LIVE_DATABENTO_ENABLED"), True),
        tradovate=tc,
    )
