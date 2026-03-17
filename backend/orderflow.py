import numpy as np
from scipy.signal import savgol_filter, argrelmin

def calculate_volume_profile(candles: list[dict]) -> dict:
    price_bins = {}
    for candle in candles:
        for price in candle["price_levels"]:
            price_bins[price] = price_bins.get(price, 0) + sum(candle["price_levels"][price])
    
    return price_bins

def calculate_low_volume_nodes(volume_profile: dict) -> list[float]:


    if len(volume_profile) < 3:
        return []

    prices = np.array(sorted(volume_profile.keys()), dtype=np.float64)
    volumes = np.array([volume_profile[p] for p in prices], dtype=np.float64)

    # Fit a smooth curve over the volume histogram
    window = min(len(prices) | 1, 11)  # must be odd, cap at 11
    if window % 2 == 0:
        window += 1
    smoothed = savgol_filter(volumes, window_length=window, polyorder=3)

    # Find local minima, excluding the first and last points
    (minima_indices,) = argrelmin(smoothed, order=1)
    minima_indices = minima_indices[(minima_indices > 0) & (minima_indices < len(prices) - 1)]

    return prices[minima_indices].tolist()