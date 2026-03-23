from collections import deque
from scipy.signal import savgol_filter

class StructureEngine:
    def __init__(self) -> None:
        self.window_length = 50
        self.polyorder = 2
        self.prices = deque(maxlen=self.window_length)
        self.prev_price: float | None = None
        self.prev_savgol: float | None = None

    def savitsky_golay(self, price) -> tuple[float, int]:
        price = float(price)
        self.prices.append(price)
        if len(self.prices) < self.window_length:
            return price, 0

        smoothed = savgol_filter(
            list(self.prices),
            window_length=self.window_length,
            polyorder=self.polyorder,
            mode="nearest",
        )
        current_savgol = float(smoothed[-1])

        # Cross detection is strictly forward-looking per candle:
        # compare previous candle vs previous savgol, and current candle vs current savgol.
        sav_condition = 0
        if self.prev_price is not None and self.prev_savgol is not None:
            was_below = self.prev_price < self.prev_savgol
            was_above = self.prev_price > self.prev_savgol
            is_above = price > current_savgol
            is_below = price < current_savgol

            if was_below and is_above:
                sav_condition = 1
            elif was_above and is_below:
                sav_condition = -1

        self.prev_price = price
        self.prev_savgol = current_savgol
        return current_savgol, sav_condition