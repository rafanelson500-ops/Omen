from collections import deque

class Microstate:
    def __init__(self, handle_signal):
        self.ticks = deque(maxlen=30)
        self.tps = 0
        self.aggression_efficiency = 0
        self.signal_callback = handle_signal

    def update(self, tick):
        self.ticks.append(tick)
        if len(self.ticks) > 1:
            time_delta = self.ticks[-1]["time"] - self.ticks[0]["time"]
            price_delta = self.ticks[-1]["close"] - self.ticks[0]["close"]
            if time_delta > 0:
                # TPS is based on intervals over elapsed time.
                self.tps = (len(self.ticks) - 1) / time_delta
                self.aggression_efficiency = price_delta / self.tps
                # print(self.aggression_efficiency)
                if self.aggression_efficiency > 0:
                    self.signal_callback(tick, 1)
            else:
                self.tps = 0