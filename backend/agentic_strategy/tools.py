from typing import Literal
from crewai.tools import tool
import requests
from dotenv import load_dotenv
import os
import json
import time
import pandas as pd
from datetime import datetime, timezone
from helpers.vp import add_value_area_levels
from helpers.data import get_data as gd

load_dotenv()

gexbot_api_key = os.getenv("GEXBOT_API_KEY")
if not gexbot_api_key or gexbot_api_key == "your-gexbot-api-key-here":
    raise EnvironmentError(
        "GEXBOT_API_KEY is not set.\n"
        "Add it to backend/.env:  GEXBOT_API_KEY=..."
    )

cache_df = None

@tool("place_trade")
def place_trade(side: Literal["BUY", "SELL"], entry_limit: float, size: Literal[1, 2, 3], stop_loss: float, take_profit: float) -> str:
    """
    Place a trade on the market with live capital.
    Args:
        side: The side of the trade (BUY or SELL)
        entry_limit: The entry limit for the trade
        size: The size of the trade (1, 2, or 3)
        stop_loss: The stop loss for the trade
        take_profit: The take profit for the trade
    Returns:
        A dictionary with the side, entry_limit, size, stop_loss, and take_profit
    """
    def round_to_tick(x):
        return round(x * 4) / 4

    entry_limit = round_to_tick(entry_limit)
    stop_loss = round_to_tick(stop_loss)
    take_profit = round_to_tick(take_profit)

    return {"side": side, "entry_limit": entry_limit, "size": size, "stop_loss": stop_loss, "take_profit": take_profit}

@tool("read_options_chain")
def read_options_chain() -> str:
    """
    Read the options chain for a given symbol.
    Args:
        symbol: The symbol of the options chain
    Returns:
        A string representation of the options chain
    """
    response = requests.get(f"https://api.gexbot.com/ES_SPX/classic/zero?key={gexbot_api_key}")
    return response.json()

@tool("get_data")
def get_data():
    """
    Get the historical OHLCV for the last 10 hours.
    Returns:
        A pandas dataframe with the historical OHLCV
    """
    global cache_df
    cache_df = gd().iloc[-120:]
    return cache_df

@tool("get_regime_data")
def get_regime_data():
    """
    Get VWAP and ATR(14) for the cached OHLCV data.

    VWAP  = cumsum(typical_price * volume) / cumsum(volume)
            where typical_price = (high + low + close) / 3

    ATR14 = 14-period Wilder smoothed average of True Range
            TR = max(high - low, |high - prev_close|, |low - prev_close|)

    Returns:
        A pandas dataframe with VWAP and ATR14 columns appended
    """
    global cache_df

    # ── VWAP ─────────────────────────────────────────────────────────────────
    typical_price = (cache_df["high"] + cache_df["low"] + cache_df["close"]) / 3
    cache_df["VWAP"] = (
        (typical_price * cache_df["volume"]).cumsum()
        / cache_df["volume"].cumsum()
    )

    # ── ATR(14) ───────────────────────────────────────────────────────────────
    prev_close = cache_df["close"].shift(1)
    tr = pd.concat([
        cache_df["high"] - cache_df["low"],
        (cache_df["high"] - prev_close).abs(),
        (cache_df["low"]  - prev_close).abs(),
    ], axis=1).max(axis=1)
    # Wilder smoothing: seed with simple mean of first 14 bars, then EWM
    cache_df["ATR14"] = tr.ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()

    return cache_df

@tool("get_order_flow_data")
def get_order_flow_data():
    """
    Get the value area levels.
    Returns:
        A pandas dataframe with the value area levels
    """
    global cache_df
    cache_df = add_value_area_levels(cache_df)
    return cache_df