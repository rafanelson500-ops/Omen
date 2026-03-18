import numpy as np
from scipy.signal import savgol_filter

def calculate_volume_profile(candles: list[dict]) -> dict:
    price_bins = {}
    for candle in candles:
        for price in candle["price_levels"]:
            price_bins[price] = price_bins.get(price, 0) + sum(candle["price_levels"][price])
    
    return price_bins

def calculate_low_volume_nodes(
    volume_profile: dict,
    eps: float = 0.05,
    curvature_threshold: float = 0.01,
) -> list[float]:

    if len(volume_profile) < 3:
        return []

    prices = np.array(sorted(volume_profile.keys()), dtype=np.float64)
    volumes = np.array([volume_profile[p] for p in prices], dtype=np.float64)

    # Normalize: z-score so LVNs are comparable across sessions
    std = volumes.std()
    if std == 0:
        return []
    volumes_norm = (volumes - volumes.mean()) / std

    # Smooth the normalized curve
    window = min(len(prices), 11)
    if window % 2 == 0:
        window -= 1
    if window < 3:
        window = 3
    smoothed = savgol_filter(volumes_norm, window_length=window, polyorder=3)

    # Curvature-based detection: flat first derivative + sharp second derivative
    first_deriv = np.gradient(smoothed)
    second_deriv = np.gradient(first_deriv)

    interior = np.arange(1, len(prices) - 1)
    lvn_mask = (
        (np.abs(first_deriv[interior]) < eps) &
        (second_deriv[interior] > curvature_threshold)
    )
    lvn_indices = interior[lvn_mask]

    # Only keep nodes where raw volume is <= 10
    return prices[lvn_indices][volumes[lvn_indices] <= 10].tolist()