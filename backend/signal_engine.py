from collections import deque
import orderflow

class SignalEngine:

    def __init__(self):
        self.long_candles = deque(maxlen=288)
        self.med_candles = deque(maxlen=60)
        self.short_candles = deque(maxlen=300)
        self.low_volume_nodes = []

    def on_tick(self, tick: dict):
        print("tick", tick)

    def on_1s(self, candle: dict):
        self.short_candles.append(candle)

        print("Low Volume Nodes")
        print(orderflow.calculate_low_volume_nodes(orderflow.calculate_volume_profile(list(self.short_candles))))

    def on_1m(self, candle: dict):
        self.med_candles.append(candle)

    def on_5m(self, candle: dict):
        self.long_candles.append(candle)