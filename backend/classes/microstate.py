from collections import deque

class Microstate:
    def __init__(self):
        self.ticks = deque(maxlen=30)
        self.tps = 0

    def update(self, tick):
        self.ticks.append(tick)
        if len(self.ticks) > 1:
            time_delta = self.ticks[-1]["time"] - self.ticks[0]["time"]
            if time_delta > 0:
                # TPS is based on intervals over elapsed time.
                self.tps = (len(self.ticks) - 1) / time_delta
            else:
                self.tps = 0
            print(self.tps)