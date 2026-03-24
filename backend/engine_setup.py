from __future__ import annotations

from collections import deque
from statistics import mean


class SetupDetector:
    """
    100-tick bar setup: combines structure + latest 10-tick micro (pressure/absorption).
    Does not require regime.tradable for scoring — strategy applies regime gate.
    """

    def __init__(self, window: int = 20) -> None:
        self.window = window
        self.candles: deque[dict[str, float]] = deque(maxlen=window)

    def update(
        self,
        candle: dict[str, float],
        microstate: dict[str, float],
        regime: dict[str, object],
    ) -> dict[str, object]:
        self.candles.append(candle)
        if len(self.candles) < 4:
            return {
                "type": None,
                "direction": None,
                "quality": 0.0,
                "reasons": ["warming_up"],
            }

        closes = [float(c["close"]) for c in self.candles]
        vols = [float(c.get("volume", 0.0)) for c in self.candles]

        recent = closes[-6:]
        diffs = [recent[i] - recent[i - 1] for i in range(1, len(recent))]
        net = recent[-1] - recent[0]
        total = sum(abs(d) for d in diffs) + 1e-9
        trend_strength = abs(net) / total
        trend_direction = "long" if net >= 0 else "short"

        pressure = float(microstate.get("pressure", 0.0))
        absorption = float(microstate.get("absorption", 0.0))
        volatility = float(microstate.get("volatility", 0.0))

        pressure_align = 1.0 if (
            (trend_direction == "long" and pressure > 0.05)
            or (trend_direction == "short" and pressure < -0.05)
        ) else 0.0

        regime_trend = str(regime.get("type") or "chop") == "trend"
        regime_boost = 0.12 if regime_trend else 0.0

        calm = max(0.0, 1.0 - min(1.0, volatility / 2.0))
        trend_score = (
            trend_strength * 0.42
            + pressure_align * 0.28
            + calm * 0.18
            + regime_boost
        )

        current_volume = vols[-1]
        avg_volume = mean(vols[-min(8, len(vols)):])
        volume_spike = current_volume / (avg_volume + 1e-9)
        body_size = abs(float(candle["close"]) - float(candle["open"]))
        bar_range = max(1e-9, float(candle["high"]) - float(candle["low"]))
        progress_ratio = body_size / bar_range

        exhaustion_direction = "short" if net > 0 else "long"
        exhaustion_pressure = (pressure < -0.05) if exhaustion_direction == "long" else (pressure > 0.05)

        exhaustion_score = (
            min(1.0, volume_spike / 1.8) * 0.38
            + (1.0 - min(1.0, progress_ratio)) * 0.28
            + absorption * 0.24
            + (0.10 if exhaustion_pressure else 0.0)
        )

        setup_type = None
        direction = None
        quality = 0.0
        reasons: list[str] = []

        # Prefer the stronger hypothesis; absorption competes with trend.
        if trend_score >= exhaustion_score and trend_score >= 0.42:
            setup_type = "trend"
            direction = trend_direction
            quality = min(1.0, trend_score)
            reasons.extend(["trend_structure", "pressure_or_calm"])
        elif exhaustion_score >= 0.40:
            setup_type = "absorption"
            direction = exhaustion_direction
            quality = min(1.0, exhaustion_score)
            reasons.extend(["volume_shape", "absorption", "exhaustion"])
        elif trend_score >= 0.36:
            setup_type = "trend"
            direction = trend_direction
            quality = min(1.0, trend_score)
            reasons.extend(["trend_marginal"])
        elif exhaustion_score >= 0.34:
            setup_type = "absorption"
            direction = exhaustion_direction
            quality = min(1.0, exhaustion_score)
            reasons.extend(["absorption_marginal"])
        else:
            reasons.append("no_setup")

        return {
            "type": setup_type,
            "direction": direction,
            "quality": float(quality),
            "reasons": reasons,
        }
