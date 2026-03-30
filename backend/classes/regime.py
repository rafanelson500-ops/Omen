import math
from collections import deque

import numpy as np


def vwap_and_std_from_sums(sum_v, sum_pv, sum_pv2):
    """
    Volume-weighted VWAP and std of price around that VWAP, from window totals.
    sum_pv = Σ(p·v), sum_pv2 = Σ(v·p²), sum_v = Σ(v). Same math as live
    ``vwap_and_std_around`` over flattened (price, volume) points.
    """
    sv = np.asarray(sum_v, dtype=np.float64)
    spv = np.asarray(sum_pv, dtype=np.float64)
    spv2 = np.asarray(sum_pv2, dtype=np.float64)
    with np.errstate(divide="ignore", invalid="ignore"):
        vw = spv / sv
        mean_p2 = spv2 / sv
        var = mean_p2 - vw * vw
    var = np.maximum(var, 0.0)
    std = np.sqrt(var)
    bad = sv <= 0
    vw = np.where(bad, np.nan, vw)
    std = np.where(bad, np.nan, std)
    return vw, std


def _candles_to_price_volume_arrays(candles):
    """Flatten candle price_levels into contiguous float64 arrays for Numba."""
    prices = []
    volumes = []
    for c in candles:
        for p, v in c["price_levels"].items():
            prices.append(float(p))
            volumes.append(float(v))
    return np.asarray(prices, dtype=np.float64), np.asarray(volumes, dtype=np.float64)


def vwap_and_std_around(candles):
    p, v = _candles_to_price_volume_arrays(candles)
    if p.size == 0:
        return float("nan"), float("nan")
    vw, s = vwap_and_std_from_sums(np.sum(v), np.sum(p * v), np.sum(v * p * p))
    return float(vw), float(s)


def vwap(candles):
    vw, _ = vwap_and_std_around(candles)
    return vw


def _efficiency_ratio_and_flips(closes):
    """
    closes: oldest .. newest, length K+1 for lookback K.
    Returns (efficiency_ratio, flip_count). ER = |net move| / sum(|bar deltas|).
    """
    n = len(closes)
    if n < 2:
        return 0.0, 0
    c0 = closes[0]
    ck = closes[-1]
    net = abs(ck - c0)
    path = 0.0
    flips = 0
    prev_sign = 0
    for i in range(1, n):
        d = closes[i] - closes[i - 1]
        path += abs(d)
        s = 1 if d > 1e-12 else (-1 if d < -1e-12 else 0)
        if s != 0 and prev_sign != 0 and s != prev_sign:
            flips += 1
        if s != 0:
            prev_sign = s
    if path < 1e-12:
        return 0.0, flips
    return net / path, flips


class Regime:
    def __init__(self):
        self.VWAP_WINDOW = 30
        self.REGIME_LOOKBACK = 28
        self.ER_CHOPPY = 0.22
        self.ER_TREND = 0.32
        self.FLIP_CHOPPY_MIN = 12
        self.FLIP_TREND_MAX = 7

        self.candles = deque(maxlen=1000)
        self.vwap = deque()
        self.vwap_std = deque()

        self.regime_label = "WARMING_UP"
        self.regime_efficiency = float("nan")
        self.regime_flips = 0

    def _append_vwap_snapshot(self, vw: float, std_around: float) -> None:
        if len(self.vwap) >= self.VWAP_WINDOW:
            self.vwap.popleft()
            self.vwap_std.popleft()
        self.vwap.append(vw)
        self.vwap_std.append(std_around)

    def _update_regime_label(self) -> None:
        k = self.REGIME_LOOKBACK
        min_bars = max(k + 1, self.VWAP_WINDOW)
        if len(self.candles) < min_bars:
            self.regime_label = "WARMING_UP"
            self.regime_efficiency = float("nan")
            self.regime_flips = 0
            return

        segment = [float(c["close"]) for c in list(self.candles)[-(k + 1) :]]
        er, flips = _efficiency_ratio_and_flips(segment)
        self.regime_efficiency = er
        self.regime_flips = flips

        raw_choppy = er < self.ER_CHOPPY or flips >= self.FLIP_CHOPPY_MIN
        raw_trend = er > self.ER_TREND and flips <= self.FLIP_TREND_MAX

        if self.regime_label == "WARMING_UP":
            if raw_choppy:
                self.regime_label = "CHOPPY"
            elif raw_trend:
                self.regime_label = "TRENDING"
            else:
                self.regime_label = "CHOPPY"
            return

        if raw_choppy:
            self.regime_label = "CHOPPY"
        elif raw_trend:
            self.regime_label = "TRENDING"

    def allows_vwap_mean_reversion(self) -> bool:
        return self.regime_label == "CHOPPY"

    def on_100th_tick(self, candle):
        self.candles.append(candle)
        vw, std_around = vwap_and_std_around(list(self.candles))
        if math.isfinite(vw) and math.isfinite(std_around):
            self._append_vwap_snapshot(vw, std_around)
        self._update_regime_label()
