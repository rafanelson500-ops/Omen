"""Feature engineering: align GEX to ES bars, compute regime + flow features."""
from __future__ import annotations

import numpy as np
import pandas as pd

from cheese.config import ES_POINT_VALUE

# Rolling lookback for z-scores in *bars* (at the bar_freq the caller picked).
FLOW_Z_WINDOW = 60      # 60 bars = 1h at 1m, 5h at 5m
WALL_TOUCH_POINTS = 2.0  # within 2 ES points counts as touching a wall


def align_gex_to_market(mkt: pd.DataFrame, gex: pd.DataFrame) -> pd.DataFrame:
    """Forward-fill GEX features onto market bar timestamps.

    We reindex GEX to the market index, forward-filling (GEX levels are
    stateful) but capping how far a value can be carried. If GEX lags the
    market by more than 2 bars, we treat that bar as stale.
    """
    if gex.empty:
        return pd.DataFrame(index=mkt.index)
    g = gex.reindex(mkt.index.union(gex.index)).sort_index().ffill(limit=2)
    return g.reindex(mkt.index)


def build_features(
    mkt: pd.DataFrame,
    gex: pd.DataFrame,
    flow_z_window: int = FLOW_Z_WINDOW,
) -> pd.DataFrame:
    """Produce the feature frame used by strategies + backtest.

    Columns added on top of OHLCV + GEX:
        atr                     - 14-bar ATR in points
        atr_pts                 - alias (convenience for strategy code)
        gamma_regime            - "long" if spot >= z_mlgamma else "short"
        dist_zero_mcall_pts     - signed distance (spot - zero_mcall), points
        dist_zero_mput_pts      - signed distance (spot - zero_mput), points
        dist_z_mlgamma_pts      - signed distance (spot - z_mlgamma), points
        crossed_mlgamma_up/dn   - bool, spot crossed z_mlgamma this bar
        touched_mcall/mput      - bool, within WALL_TOUCH_POINTS of wall
        broke_mcall_up          - bool, crossed zero_mcall upward this bar
        broke_mput_dn           - bool, crossed zero_mput downward this bar
        gexoflow_z              - rolling z-score of gexoflow_sum
        dexoflow_z              - rolling z-score of dexoflow_sum
    """
    df = mkt.join(align_gex_to_market(mkt, gex), how="left")

    # ATR in points
    h, l, c = df["high"], df["low"], df["close"]
    pc = c.shift(1)
    tr = pd.concat([(h - l), (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    df["atr"] = tr.rolling(14, min_periods=5).mean()
    df["atr_pts"] = df["atr"]

    # Regime + distances (only where GEX is present)
    spot = df.get("spot")
    if spot is not None:
        df["gamma_regime"] = np.where(spot >= df.get("z_mlgamma"), "long", "short")
        df["dist_zero_mcall_pts"] = spot - df.get("zero_mcall")
        df["dist_zero_mput_pts"] = spot - df.get("zero_mput")
        df["dist_z_mlgamma_pts"] = spot - df.get("z_mlgamma")

        prev_sign = np.sign(df["dist_z_mlgamma_pts"].shift(1))
        cur_sign = np.sign(df["dist_z_mlgamma_pts"])
        df["crossed_mlgamma_up"] = (prev_sign < 0) & (cur_sign >= 0)
        df["crossed_mlgamma_dn"] = (prev_sign > 0) & (cur_sign <= 0)

        # Wall touches (price within N points of a wall on this bar's range)
        within = lambda wall: (df["low"] <= wall + WALL_TOUCH_POINTS) & (df["high"] >= wall - WALL_TOUCH_POINTS)
        df["touched_mcall"] = within(df["zero_mcall"]) if "zero_mcall" in df else False
        df["touched_mput"] = within(df["zero_mput"]) if "zero_mput" in df else False

        # Breaks: close crossed the wall this bar
        df["broke_mcall_up"] = (c.shift(1) <= df["zero_mcall"].shift(1)) & (c > df["zero_mcall"])
        df["broke_mput_dn"] = (c.shift(1) >= df["zero_mput"].shift(1)) & (c < df["zero_mput"])

    # Flow z-scores
    for col in ("gexoflow_sum", "dexoflow_sum", "cvroflow_sum"):
        if col not in df.columns:
            continue
        mu = df[col].rolling(flow_z_window, min_periods=flow_z_window // 3).mean()
        sd = df[col].rolling(flow_z_window, min_periods=flow_z_window // 3).std(ddof=0)
        df[col.replace("_sum", "_z")] = (df[col] - mu) / sd.replace(0, np.nan)

    return df


def dollar_pnl_per_point() -> float:
    """Convenience: $ per ES point per contract."""
    return ES_POINT_VALUE
