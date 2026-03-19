import numpy as np
from collections import deque
from scipy.signal import savgol_filter


class OrderflowEngine:
    def __init__(
        self,
        absorption_window: int = 100,
        vol_threshold: float = 30,
        lvn_eps: float = 0.05,
        lvn_curvature: float = 0.01,
    ):
        # --- Absorption state ---
        self.abs_window = absorption_window
        self.vol_threshold = vol_threshold

        self.abs_values = deque(maxlen=absorption_window)
        self.abs_sum = 0.0
        self.abs_sum_sq = 0.0

        # --- Volume profile state ---
        self.price_bins = {}

        # --- LVN params ---
        self.lvn_eps = lvn_eps
        self.lvn_curvature = lvn_curvature

    # =========================
    # 🔹 UPDATE (main entry point)
    # =========================
    def update(self, candle: dict) -> dict:
        """
        Call this every new candle.
        Returns computed features.
        """
        self._update_volume_profile(candle)
        absorption = self._update_absorption(candle)

        return {
            "absorption_z": absorption * 1e4,
        }

    # =========================
    # 🔹 ABSORPTION
    # =========================
    def _update_absorption(self, candle: dict) -> float:
        buy = candle["buy_volume"]
        sell = candle["sell_volume"]

        total_vol = buy + sell
        if total_vol < self.vol_threshold:
            return 0.0

        delta = buy - sell
        price_move = max(candle["high"] - candle["low"], 1e-6)
        body = abs(candle["close"] - candle["open"])

        # Effort: how imbalanced the flow was (-1 to +1)
        #   +1 = all buys, -1 = all sells
        delta_norm = delta / (total_vol + 1e-6)

        # Result: how much of the range became net price movement (0 to 1)
        #   1 = full-bodied candle (price moved completely with flow)
        #   0 = doji / spinning top (price went nowhere despite activity)
        result_norm = body / price_move

        # Absorption = effort that didn't produce a result
        #   val > 0 → buy delta with weak body (sellers absorbing buys, bearish)
        #   val < 0 → sell delta with weak body (buyers absorbing sells, bullish)
        #   val ≈ 0 → impulsive candle (price moved fully with delta, no absorption)
        val = delta_norm * (1.0 - result_norm)

        # --- Remove old ---
        if len(self.abs_values) == self.abs_window:
            old = self.abs_values.popleft()
            self.abs_sum -= old
            self.abs_sum_sq -= old * old

        # --- Add new ---
        self.abs_values.append(val)
        self.abs_sum += val
        self.abs_sum_sq += val * val

        # --- Compute z-score ---
        n = len(self.abs_values)
        mean = self.abs_sum / n
        var = (self.abs_sum_sq / n) - (mean * mean)
        std = np.sqrt(max(var, 1e-8))

        z = (val - mean) / std
        return z

    # =========================
    # 🔹 VOLUME PROFILE
    # =========================
    def _update_volume_profile(self, candle: dict):
        for price, vols in candle["price_levels"].items():
            self.price_bins[price] = self.price_bins.get(price, 0) + (vols[0] + vols[1])

    def get_volume_profile(self) -> dict:
        return self.price_bins

    # =========================
    # 🔹 LOW VOLUME NODES (LVN)
    # =========================
    def get_low_volume_nodes(self) -> list[float]:
        volume_profile = self.price_bins

        if len(volume_profile) < 3:
            return []

        prices = np.array(sorted(volume_profile.keys()), dtype=np.float64)
        volumes = np.array([volume_profile[p] for p in prices], dtype=np.float64)

        std = volumes.std()
        if std == 0:
            return []

        volumes_norm = (volumes - volumes.mean()) / std

        window = min(len(prices), 11)
        if window % 2 == 0:
            window -= 1
        if window < 3:
            window = 3

        smoothed = savgol_filter(volumes_norm, window_length=window, polyorder=3)

        first_deriv = np.gradient(smoothed)
        second_deriv = np.gradient(first_deriv)

        interior = np.arange(1, len(prices) - 1)

        lvn_mask = (
            (np.abs(first_deriv[interior]) < self.lvn_eps)
            & (second_deriv[interior] > self.lvn_curvature)
        )

        lvn_indices = interior[lvn_mask]

        # Optional strict filter (can tune/remove)
        return prices[lvn_indices][volumes[lvn_indices] <= 10].tolist()