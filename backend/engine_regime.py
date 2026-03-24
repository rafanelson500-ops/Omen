from __future__ import annotations

from collections import deque
from statistics import mean


class RegimeFilter:
    """10-tick bar regime: volatility bucket + trend vs chop (soft), not a hard trade ban."""

    def __init__(self, window: int = 24) -> None:
        self.window = window
        self.closes: deque[float] = deque(maxlen=window + 1)
        self.ranges: deque[float] = deque(maxlen=window)

    def update(self, candle: dict[str, float]) -> dict[str, object]:
        close = float(candle["close"])
        high = float(candle["high"])
        low = float(candle["low"])
        self.closes.append(close)
        self.ranges.append(max(0.0, high - low))

        if len(self.closes) < 6:
            return {
                "tradable": False,
                "type": "chop",
                "volatility": "low",
                "direction_consistency": 0.0,
                "movement_ratio": 0.0,
                "avg_swing_size": 0.0,
                "reasons": ["warming_up"],
            }

        diffs = [self.closes[i] - self.closes[i - 1] for i in range(1, len(self.closes))]
        net_move = self.closes[-1] - self.closes[0]
        total_move = sum(abs(d) for d in diffs) + 1e-9
        movement_ratio = abs(net_move) / total_move

        positive = sum(1 for d in diffs if d > 0)
        negative = sum(1 for d in diffs if d < 0)
        direction_consistency = max(positive, negative) / max(1, len(diffs))
        avg_swing = mean(abs(d) for d in diffs)
        avg_range = mean(self.ranges) if self.ranges else 0.0

        # Calibrated for index futures tick ranges on aggregated bars (not absolute $).
        if avg_range < 2.0:
            vol_bucket = "low"
        elif avg_range < 12.0:
            vol_bucket = "medium"
        else:
            vol_bucket = "high"

        regime_type = "trend" if movement_ratio >= 0.38 else "chop"

        # Tradable unless vol is extreme — chop is still valid for mean-reversion setups.
        tradable = vol_bucket != "high"

        reasons: list[str] = []
        if regime_type != "trend":
            reasons.append("regime_chop")
        else:
            reasons.append("regime_trend")
        if vol_bucket == "high":
            reasons.append("volatility_too_high")
        if not reasons:
            reasons.append("regime_ok")

        return {
            "tradable": tradable,
            "type": regime_type,
            "volatility": vol_bucket,
            "direction_consistency": float(direction_consistency),
            "movement_ratio": float(movement_ratio),
            "avg_swing_size": float(avg_swing),
            "reasons": reasons,
        }
