from engine_datastream import DatastreamEngine
from flask import Flask
from flask_socketio import SocketIO
from heikin_ashi import HeikinAshi

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")


def main():
    datastream = DatastreamEngine()
    heikin_ashi_10 = HeikinAshi()
    heikin_ashi_100 = HeikinAshi()

    trigger = 0

    def is_green(candle):
        return candle["close"] > candle["open"]

    def on_tick(candle):
        nonlocal trigger
        if trigger == -1:
            print("Short @ ", candle["close"])
            trigger = 0
        elif trigger == 1:
            print("Long @ ", candle["close"])
            trigger = 0

        socketio.emit("1-tick", candle)

    def on_10th_tick(candle):
        ha = heikin_ashi_10.ohlc_to_ha(candle)

        socketio.emit("10-tick", ha)

    def on_100th_tick(candle):
        nonlocal trigger
        last_ha = heikin_ashi_100.last_ha
        ha = heikin_ashi_100.ohlc_to_ha(candle)

        if last_ha is not None:
            if is_green(last_ha) and not is_green(ha):
                trigger = -1
            elif not is_green(last_ha) and is_green(ha):
                trigger = 1

        socketio.emit("100-tick", ha)

    datastream.subscribe(1, on_tick)
    datastream.subscribe(10, on_10th_tick)
    datastream.subscribe(100, on_100th_tick)
    datastream.start(simulated=True)


if __name__ == "__main__":
    main()
    socketio.run(app, host="0.0.0.0", port=8000)
