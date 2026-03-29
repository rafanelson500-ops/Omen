from collections import deque

class Microstate:
    def __init__(self, push_signal):
        self.WINDOW = 30
        self.MULTI_PRINT_THRESHOLD = 5

        self.ticks = deque(maxlen=30)
        self.tps = deque()
        self.aggression_efficiency = deque()
        self.push_signal_callback = push_signal

        self._tps_sum = 0.0
        self.average_tps = 0.0
        self._agg_sum = 0.0
        self._agg_sum_sq = 0.0
        self._agg_extreme_zone = "inside"  # "inside" | "plus" | "minus" — edge-trigger signals
        self._tps_spike_active = False
        self.streak = 0

    def update(self, tick):
        self.ticks.append(tick)
        ts = tick["time"]
        if len(self.ticks) > 1:

            # TPS & Aggression Efficiency
            time_delta = self.ticks[-1]["time"] - self.ticks[0]["time"]
            price_delta = self.ticks[-1]["close"] - self.ticks[0]["close"]
            if time_delta > 0:
                # TPS is based on intervals over elapsed time.
                self.tps.append((len(self.ticks) - 1) / time_delta)
                tps_now = self.tps[-1]
                self._tps_sum += tps_now
                if len(self.tps) > self.WINDOW:
                    self._tps_sum -= self.tps.popleft()
                self.average_tps = self._tps_sum / len(self.tps)

                aggeff_now = price_delta / tps_now
                self.aggression_efficiency.append(aggeff_now)
                self._agg_sum += aggeff_now
                self._agg_sum_sq += aggeff_now * aggeff_now
                if len(self.aggression_efficiency) > self.WINDOW:
                    old_agg = self.aggression_efficiency.popleft()
                    self._agg_sum -= old_agg
                    self._agg_sum_sq -= old_agg * old_agg

                n_agg = len(self.aggression_efficiency)
                zone = "inside"
                if n_agg >= 2:
                    mean_agg = self._agg_sum / n_agg
                    var_agg = self._agg_sum_sq / n_agg - mean_agg * mean_agg
                    if var_agg > 0:
                        std_agg = var_agg**0.5
                        if aggeff_now > mean_agg + 2 * std_agg:
                            zone = "plus"
                        elif aggeff_now < mean_agg - 2 * std_agg:
                            zone = "minus"
                if zone == "plus" and self._agg_extreme_zone != "plus":
                    self.push_signal_callback("+ Aggression Extreme", ts)
                elif zone == "minus" and self._agg_extreme_zone != "minus":
                    self.push_signal_callback("- Aggression Extreme", ts)
                self._agg_extreme_zone = zone

                tps_spike_now = tps_now > self.average_tps * 2
                if tps_spike_now and not self._tps_spike_active:
                    self.push_signal_callback("TPS Spike", ts)
                self._tps_spike_active = tps_spike_now

            # Multi-Prints
            if tick["close"] == self.ticks[-2]["close"]:
                self.streak += 1
            else:
                self.streak = 0

            if self.streak > self.MULTI_PRINT_THRESHOLD:
                self.push_signal_callback("Multi-Print", ts)
                self.streak = -100