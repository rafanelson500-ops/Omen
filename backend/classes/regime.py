import math
from collections import deque

import numpy as np
from numba import njit


def _candles_to_price_volume_arrays(candles):
    """Flatten candle price_levels into contiguous float64 arrays for Numba."""
    prices = []
    volumes = []
    for c in candles:
        for p, v in c["price_levels"].items():
            prices.append(float(p))
            volumes.append(float(v))
    return np.asarray(prices, dtype=np.float64), np.asarray(volumes, dtype=np.float64)


@njit(cache=True)
def vwap_and_std_around_from_arrays(prices, volumes):
    """VWAP and volume-weighted std of price around that VWAP (same window)."""
    n = prices.shape[0]
    vwap_total = 0.0
    pv2_total = 0.0
    total_volume = 0.0
    for i in range(n):
        pi = prices[i]
        vi = volumes[i]
        vwap_total += pi * vi
        pv2_total += vi * pi * pi
        total_volume += vi
    if total_volume == 0.0:
        return np.nan, np.nan
    vw = vwap_total / total_volume
    mean_p2 = pv2_total / total_volume
    var = mean_p2 - vw * vw
    if var < 0.0:
        var = 0.0
    std_around = np.sqrt(var)
    return vw, std_around


def vwap_and_std_around(candles):
    p, v = _candles_to_price_volume_arrays(candles)
    vw, s = vwap_and_std_around_from_arrays(p, v)
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
