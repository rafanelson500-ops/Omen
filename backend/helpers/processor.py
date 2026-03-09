import numpy as np

# ── Signal thresholds ─────────────────────────────────────────────────────────
# New strategy: When |gbt| < 0.5 (model uncertain), trade according to trend slope
# gbt ∈ [-5, +5] :  |gbt| < 0.5 → model uncertain, follow trend
GBT_UNCERTAIN_THRESH = 0.3  # if |gbt| < this, model is uncertain → follow trend


def process_data(df):
    # ── Buy-and-hold baseline ──────────────────────────────────────────────────
    df["base_returns"] = df["close"] - df["close"].shift(1)
    df["base_returns"] = np.where(df["new_session"] == 1, 0, df["base_returns"])

    gbt = df["gbt_target"].fillna(0).values.astype(np.float64)

    # ── New Strategy: Trend-following when model is uncertain ───────────────────
    # If |gbt| < 0.5 (model is uncertain), trade according to trend slope
    # Trend: use simple close vs EMA (positive = above EMA = uptrend, negative = below EMA = downtrend)
    ema_vals = df["ema"].fillna(df["close"]).values.astype(np.float64)
    close_vals = df["close"].values.astype(np.float64)
    trend = close_vals - ema_vals  # positive = uptrend, negative = downtrend
    
    # Signal: if |gbt| < GBT_UNCERTAIN_THRESH, trade in direction of trend
    gbt_abs = np.abs(gbt)
    df["position"] = np.where(gbt_abs < GBT_UNCERTAIN_THRESH, -np.sign(trend), 0)

    df["strategy_returns"]    = df["base_returns"] * df["position"].shift(1)
    df["base_cumulative"]     = df["base_returns"].cumsum()
    df["strategy_cumulative"] = df["strategy_returns"].cumsum()

    return df
