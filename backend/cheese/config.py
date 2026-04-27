"""Shared configuration: paths, constants, cost model, dataclasses."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from zoneinfo import ZoneInfo

BACKEND_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = BACKEND_ROOT / "data"
GEX_CACHE = DATA_DIR / "gex"
MARKET_CACHE = DATA_DIR / "market"
for _d in (GEX_CACHE, MARKET_CACHE):
    _d.mkdir(parents=True, exist_ok=True)

ET = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")

# ES front-month continuous, CME Globex
DATABENTO_DATASET = "GLBX.MDP3"
ES_CONTINUOUS_SYMBOL = "ES.c.0"  # front-month continuous, daily roll at expiry

# ES contract mechanics
ES_TICK_SIZE = 0.25            # points
ES_TICK_VALUE = 12.50          # $ per tick per contract
ES_POINT_VALUE = 50.0          # $ per point per contract ($12.50 / 0.25)


def round_to_tick(price: float, tick: float = ES_TICK_SIZE) -> float:
    """Round a price to the nearest exchange tick (default ES = 0.25).

    Uses half-away-from-zero to avoid bank-rounding surprises at ties, then
    normalises to 2 decimals so string formatting and equality checks are
    clean (e.g. 5910.249999 -> 5910.25 exactly).
    """
    if tick <= 0:
        return float(price)
    n_ticks = int((price / tick) + (0.5 if price >= 0 else -0.5))
    return round(n_ticks * tick, 2)

# Regular trading hours (SPX cash session = where GEX data is live)
RTH_OPEN = "09:30"
RTH_CLOSE = "16:00"

@dataclass(frozen=True)
class Instrument:
    name: str
    tick_size: float
    tick_value: float
    point_value: float

INSTRUMENTS = {
    "ES": Instrument("ES", 0.25, 12.50, 50.0),
    "MES": Instrument("MES", 0.25, 1.25, 5.0),
}


@dataclass(frozen=True)
class CostModel:
    """Round-trip execution cost model for ES front-month.

    Applied symmetrically on entry + exit. Slippage is in ticks and converted
    to $ via ES_TICK_VALUE. Commission is $ per side.

    First/last 15 minutes of RTH apply `edge_slippage_mult` to slippage.
    """
    commission_per_side: float = 2.50
    slippage_ticks_per_side: float = 0.5      # half a tick each side => 1 tick RT
    edge_slippage_mult: float = 2.0           # first/last 15 min of RTH

    def per_side_cost_dollars(self, on_session_edge: bool = False) -> float:
        slip_ticks = self.slippage_ticks_per_side * (self.edge_slippage_mult if on_session_edge else 1.0)
        return self.commission_per_side + slip_ticks * ES_TICK_VALUE


@dataclass(frozen=True)
class ExitConfig:
    """ATR-based stop/target with trailing + time cap."""
    atr_window_bars: int = 14
    stop_atr_mult: float = 2.0
    target_atr_mult: float = 4.5
    trail_after_r: float = 0         # once price is 1R in favor, ratchet stop to breakeven
    time_stop_min: int = 25            # hard close after N minutes in position
    close_at_rth_end: bool = True      # force flat at 15:55 ET


@dataclass(frozen=True)
class BacktestConfig:
    bar_freq: str = "1min"             # 1min or 5min
    feature_lookback_bars: int = 20    # for z-scores, ATR warmup, etc.
    max_concurrent_positions: int = 1  # no pyramiding
    instrument: str = "ES"             # "ES" or "MES"
    sizing_mode: str = "static"        # "static" or "kelly"
    static_quantity: int = 1           # lot size when sizing_mode="static"
    account_size: float = 100000.0     # starting capital for dynamic sizing
    kelly_fraction: float = 1.0        # Kelly fraction multiplier
    cost: CostModel = field(default_factory=CostModel)
    exits: ExitConfig = field(default_factory=ExitConfig)


__all__ = [
    "BACKEND_ROOT", "DATA_DIR", "GEX_CACHE", "MARKET_CACHE",
    "ET", "UTC",
    "DATABENTO_DATASET", "ES_CONTINUOUS_SYMBOL",
    "Instrument", "INSTRUMENTS",
    "ES_TICK_SIZE", "ES_TICK_VALUE", "ES_POINT_VALUE", "round_to_tick",
    "RTH_OPEN", "RTH_CLOSE",
    "CostModel", "ExitConfig", "BacktestConfig",
]
