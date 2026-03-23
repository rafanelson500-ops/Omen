from collections import deque
from scipy.signal import savgol_filter

class StructureEngine:
    def __init__(self) -> None:
        self.window_length = 50
        self.polyorder = 2
        self.prices = deque(maxlen=self.window_length)
        self.prev_sav_condition = 0

    def savitsky_golay(self, price) -> float:
        self.prices.append(float(price))
        if len(self.prices) < self.window_length:
            return price

        smoothed = savgol_filter(
            list(self.prices),
            window_length=self.window_length,
            polyorder=self.polyorder,
            mode="nearest",
        )
        if smoothed[-1] < price and self.prev_sav_condition != 1:
            self.prev_sav_condition = 1
        elif smoothed[-1] > price and self.prev_sav_condition != -1:
            self.prev_sav_condition = -1
        else:
            self.prev_sav_condition = 0
        return float(smoothed[-1]), self.prev_sav_condition