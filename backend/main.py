from engine_datastream import DatastreamEngine
from flask import Flask
from flask_socketio import SocketIO

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")


def main():
    datastream = DatastreamEngine()

    def on_tick(candle):
        socketio.emit("1-tick", candle)

    def on_10th_tick(candle):
        socketio.emit("10-tick", candle)

    def on_100th_tick(candle):
        socketio.emit("100-tick", candle)

    datastream.subscribe(1, on_tick)
    datastream.subscribe(10, on_10th_tick)
    datastream.subscribe(100, on_100th_tick)
    datastream.start(simulated=True, speed=1)


if __name__ == "__main__":
    main()
    socketio.run(app, host="0.0.0.0", port=8000)
