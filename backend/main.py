from engine_datastream import DatastreamEngine
from flask import Flask
from flask_socketio import SocketIO
from heikin_ashi import HeikinAshi
from engine_structure import StructureEngine

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")


def main():
    datastream = DatastreamEngine()
    structure = StructureEngine()

    def on_tick(candle):
        socketio.emit("1-tick", candle)

    def on_10th_tick(candle):
        socketio.emit("10-tick", candle)

    def on_100th_tick(candle):
        sav_price, sav_condition = structure.savitsky_golay(candle["close"])
        candle["savgol"] = sav_price
        socketio.emit("100-tick", candle)

    datastream.subscribe(1, on_tick)
    datastream.subscribe(10, on_10th_tick)
    datastream.subscribe(100, on_100th_tick)
    datastream.start(simulated=True, speed=10)


if __name__ == "__main__":
    main()
    socketio.run(app, host="0.0.0.0", port=8000)
