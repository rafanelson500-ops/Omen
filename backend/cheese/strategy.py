"""Signal generators.

Every strategy takes the feature frame produced by ``features.build_features``
and returns a pandas Series of desired positions indexed by the same bars:
    +1  -> go long at the OPEN of the next bar
    -1  -> go short at the OPEN of the next bar
     0  -> no signal this bar

The backtester handles holding logic, stops, and exits. A strategy should
NOT try to manage trades; it just emits entry intents.

Strategies included:
    FlowBurstStrategy           - gexoflow / dexoflow z-score spike
    WallRejectStrategy          - fade touches of walls in long-gamma regime
    WallBreakStrategy           - trade wall breaks with flow confirmation
    RegimeFlipStrategy          - zero-gamma flip, trend-follow the direction
    RandomStrategy              - coin-flip baseline
    BuyHoldStrategy             - always long during RTH (naive baseline)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np
import pandas as pd


class Strategy(Protocol):
    name: str
    def signals(self, feat: pd.DataFrame) -> pd.Series: ...


def _zero_series(feat: pd.DataFrame) -> pd.Series:
    return pd.Series(0, index=feat.index, dtype="int8")


@dataclass
class FlowBurstStrategy:
    """Enter in direction of an abnormal flow burst.

    gexoflow_z > z_threshold AND dexoflow_z same sign -> long (flow is buying gamma + buying delta).
    Symmetric short on the other side. Only fires when gamma_regime available.
    """
    z_threshold: float = 2.0
    name: str = "flow_burst"

    def signals(self, feat: pd.DataFrame) -> pd.Series:
        s = _zero_series(feat)
        if "gexoflow_z" not in feat or "dexoflow_z" not in feat:
            return s
        gz, dz = feat["gexoflow_z"], feat["dexoflow_z"]
        long_ = (gz > self.z_threshold) & (dz > 0)
        short_ = (gz < -self.z_threshold) & (dz < 0)
        s.loc[long_.fillna(False)] = 1
        s.loc[short_.fillna(False)] = -1
        return s


@dataclass
class WallRejectStrategy:
    """Fade wall touches during positive-gamma (mean-revert) regime.

    Long the put wall touch, short the call wall touch, only when spot is
    above zero_gamma (long-gamma, vol-suppression regime).
    """
    name: str = "wall_reject"

    def signals(self, feat: pd.DataFrame) -> pd.Series:
        s = _zero_series(feat)
        if "gamma_regime" not in feat:
            return s
        pos_gamma = feat["gamma_regime"].eq("long").fillna(False)
        long_ = pos_gamma & feat.get("touched_mput", False).fillna(False)
        short_ = pos_gamma & feat.get("touched_mcall", False).fillna(False)
        s.loc[long_] = 1
        s.loc[short_] = -1
        return s


@dataclass
class WallBreakStrategy:
    """Trade breakouts through walls when orderflow confirms direction."""
    min_flow_z: float = 1.0
    name: str = "wall_break"

    def signals(self, feat: pd.DataFrame) -> pd.Series:
        s = _zero_series(feat)
        if "gexoflow_z" not in feat:
            return s
        gz = feat["gexoflow_z"].fillna(0)
        long_ = feat.get("broke_mcall_up", False).fillna(False) & (gz >= self.min_flow_z)
        short_ = feat.get("broke_mput_dn", False).fillna(False) & (gz <= -self.min_flow_z)
        s.loc[long_] = 1
        s.loc[short_] = -1
        return s


@dataclass
class RegimeFlipStrategy:
    """Trade the direction of the zero-gamma flip (spot crossing z_mlgamma)."""
    name: str = "regime_flip"

    def signals(self, feat: pd.DataFrame) -> pd.Series:
        s = _zero_series(feat)
        long_ = feat.get("crossed_mlgamma_up", False).fillna(False)
        short_ = feat.get("crossed_mlgamma_dn", False).fillna(False)
        s.loc[long_] = 1
        s.loc[short_] = -1
        return s


@dataclass
class RandomStrategy:
    """Coin-flip baseline: same # of entries as a target strategy, random side."""
    probability: float = 0.01
    seed: int = 7
    name: str = "random"

    def signals(self, feat: pd.DataFrame) -> pd.Series:
        rng = np.random.default_rng(self.seed)
        draws = rng.random(len(feat))
        sign = rng.choice([-1, 1], size=len(feat)).astype("int8")
        out = np.where(draws < self.probability, sign, 0).astype("int8")
        return pd.Series(out, index=feat.index)


@dataclass
class BuyHoldStrategy:
    """Naive baseline: long at first RTH bar each session, exit at close."""
    name: str = "buy_hold"

    def signals(self, feat: pd.DataFrame) -> pd.Series:
        s = _zero_series(feat)
        date_idx = feat.index.date
        first_of_day = np.concatenate(([True], date_idx[1:] != date_idx[:-1]))
        s.loc[first_of_day] = 1
        return s


ALL_STRATEGIES: dict[str, type] = {
    "flow_burst": FlowBurstStrategy,
    "wall_reject": WallRejectStrategy,
    "wall_break": WallBreakStrategy,
    "regime_flip": RegimeFlipStrategy,
    "random": RandomStrategy,
    "buy_hold": BuyHoldStrategy,
}
