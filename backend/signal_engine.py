from collections import deque
from orderflow import OrderflowEngine
from flask_socketio import SocketIO

class SignalEngine:

    def __init__(self, socketio: SocketIO):
        self.socketio = socketio
        self.long_candles = deque(maxlen=288)
        self.med_candles = deque(maxlen=60)
        self.short_candles = deque(maxlen=300)

        self.orderflow_short = OrderflowEngine(absorption_window=100)
        self.orderflow_med = OrderflowEngine(absorption_window=60)
        self.orderflow_long = OrderflowEngine(absorption_window=288)

    def on_tick(self, tick: dict):
        self.socketio.emit("tick", tick)

    def on_1s(self, candle: dict):
        self.short_candles.append(candle)
        features = self.orderflow_short.update(candle)
        self.socketio.emit("short_candle", {**candle, "graph:1:red:absorption_z": features["absorption_z"]})

    def on_1m(self, candle: dict):
        self.med_candles.append(candle)
        features = self.orderflow_med.update(candle)
        self.socketio.emit("med_candle", {**candle, "graph:1:red:absorption_z": features["absorption_z"]})

    def on_5m(self, candle: dict):
        self.long_candles.append(candle)
        self.orderflow_long.update(candle)

        lvns = self.orderflow_long.get_low_volume_nodes()
        print("Low Volume Nodes")
        print(lvns)
        self.socketio.emit("lvn_update", lvns)
        self.socketio.emit("long_candle", candle)
