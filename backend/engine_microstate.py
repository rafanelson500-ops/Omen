from __future__ import annotations

from collections import deque
import math
from statistics import pstdev
from typing import Any


def _side_sign(raw_side: Any) -> int:
    side = str(raw_side or "").upper()
    if side in {"B", "BUY"}:
        return 1
    if side in {"A", "S", "SELL"}:
        return -1
    return 0


class MicrostateEngine:
    def __init__(self, window: int = 40) -> None:
        self.window = window
        self.prices: deque[float] = deque(maxlen=window)
        self.signed_sizes: deque[float] = deque(maxlen=window)
        self.sizes: deque[float] = deque(maxlen=window)

    def update(self, tick_payload: dict[str, Any]) -> dict[str, float]:
        price = float(tick_payload.get("close", tick_payload.get("price", 0.0)))
        size = float(tick_payload.get("size", 0.0))
        side = _side_sign(tick_payload.get("side"))

        self.prices.append(price)
        self.sizes.append(size)
        self.signed_sizes.append(size * side)

        total_volume = sum(self.sizes)
        signed_volume = sum(self.signed_sizes)
        delta_imbalance = signed_volume / (total_volume + 1e-9)

        if len(self.prices) >= 2:
            price_move = self.prices[-1] - self.prices[0]
            tick_changes = [
                self.prices[i] - self.prices[i - 1] for i in range(1, len(self.prices))
            ]
            volatility = pstdev(tick_changes) if len(tick_changes) > 1 else abs(tick_changes[0])
        else:
            price_move = 0.0
            volatility = 0.0

        price_response = abs(price_move) / (total_volume + 1e-9)
        volume_ratio = min(1.0, total_volume / max(1.0, self.window * 2.0))
        movement_penalty = min(1.0, abs(price_move) / 2.0)
        absorption_score = max(0.0, min(1.0, volume_ratio * (1.0 - movement_penalty)))

        # Pressure is directionally signed and capped to [-1, 1].
        pressure = math.tanh((delta_imbalance * 2.2) + (price_move * 1.3))

        return {
            "pressure": float(max(-1.0, min(1.0, pressure))),
            "absorption": float(absorption_score),
            "volatility": float(volatility),
            "delta_imbalance": float(delta_imbalance),
            "price_response": float(price_response),
        }
