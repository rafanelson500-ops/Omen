from collections import deque
import orderflow
from flask_socketio import SocketIO

class SignalEngine:

    def __init__(self, socketio: SocketIO):
        self.socketio = socketio
        self.long_candles = deque(maxlen=288)
        self.med_candles = deque(maxlen=60)
        self.short_candles = deque(maxlen=300)
        self.low_volume_nodes = []

    def on_tick(self, tick: dict):
        self.socketio.emit("tick", tick)

    def on_1s(self, candle: dict):
        self.short_candles.append(candle)
        self.socketio.emit("short_candle", candle)

    def on_1m(self, candle: dict):
        self.med_candles.append(candle)
        self.socketio.emit("med_candle", candle)

    def on_5m(self, candle: dict):
        self.long_candles.append(candle)

        print("Low Volume Nodes")
        lvns = orderflow.calculate_low_volume_nodes(orderflow.calculate_volume_profile(list(self.long_candles)))
        print(lvns)
        self.socketio.emit("lvn_update", lvns)
        self.socketio.emit("long_candle", candle)