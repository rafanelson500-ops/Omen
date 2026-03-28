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


class Regime:
    def __init__(self):
        self.VWAP_WINDOW = 30

        self.candles = deque(maxlen=1000)
        self.vwap = deque()
        self.vwap_std = deque()

    def _append_vwap_snapshot(self, vw: float, std_around: float) -> None:
        if len(self.vwap) >= self.VWAP_WINDOW:
            self.vwap.popleft()
            self.vwap_std.popleft()
        self.vwap.append(vw)
        self.vwap_std.append(std_around)

    def on_100th_tick(self, candle):
        self.candles.append(candle)
        vw, std_around = vwap_and_std_around(list(self.candles))
        if math.isfinite(vw) and math.isfinite(std_around):
            self._append_vwap_snapshot(vw, std_around)
