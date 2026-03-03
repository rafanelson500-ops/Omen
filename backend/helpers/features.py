import numpy as np
import pandas as pd
import time
from scipy.stats import kurtosis
from helpers.vp import add_value_area_levels


def add_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    # ── Log returns (internal; used by all features below) ───────────────────
    print("[Features] Computing log returns...")
    start_time = time.time()
    log_ret = np.log(df["close"] / df["close"].shift(1))
    print(f"[Features] Log returns computed in {time.time() - start_time:.3f}s")

    df["new_session"] = np.where(((df.index.hour == 14) & (df.index.minute == 30)) | ((df.index.hour == 23) & (df.index.minute == 0)), 1, 0)

    # ── Session VWAP ────────────────────────────────────────────────────────────
    print("[Features] Computing session VWAP...")
    start_time = time.time()
    
    # Create session IDs that increment at each new session
    session_id = df["new_session"].cumsum()
    
    # Calculate typical price
    typical_price = (df["high"] + df["low"] + df["close"]) / 3
    
    # Calculate session VWAP: cumsum(typical_price * volume) / cumsum(volume) per session
    # Group by session and calculate cumulative sums within each session
    df["session_vwap"] = (
        df.groupby(session_id)
        .apply(lambda g: (typical_price.loc[g.index] * df.loc[g.index, "volume"]).cumsum() / df.loc[g.index, "volume"].cumsum())
        .droplevel(0)
        .reindex(df.index)
    )
    
    print(f"[Features] Session VWAP computed in {time.time() - start_time:.3f}s")

    # ── EMA ─────────────────────────────────────────────────────────────────────
    print("[Features] Computing EMA...")
    start_time = time.time()
    
    # Calculate EMA(20) on close price
    df["ema_20"] = df["close"].ewm(span=20, adjust=False).mean()
    df = add_value_area_levels(df)

    df["ema_vwap_spread"] = abs(df["session_vwap"] - df["ema_20"])
    df["vwap_poc_spread"] = abs(df["session_vwap"] - df["poc"])
    df["poc_ema_spread"] = abs(df["poc"] - df["ema_20"])
    
    print(f"[Features] EMA computed in {time.time() - start_time:.3f}s")

    return df
