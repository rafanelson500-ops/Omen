from engine_datastream import DatastreamEngine
from paper_trader import PaperTrader
from flask import Flask
from flask_socketio import SocketIO

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")


def main():
    datastream = DatastreamEngine()

    def emit_trade(event: str, payload: dict) -> None:
        socketio.emit(event, payload)

    trader = PaperTrader(emit_trade)

    def on_tick(tick):
        trader.on_tick(tick)
        socketio.emit("tick", tick)

    def on_wall_delta(delta):
        trader.on_wall_delta(delta)
        if delta.get("added") or delta.get("removed"):
            socketio.emit("wall_delta", delta)

    datastream.subscribe_tick(on_tick)
    datastream.subscribe_mbp(on_wall_delta)
    trader.reset()
    datastream.start_simulated()


if __name__ == "__main__":
    main()
    socketio.run(app, host="0.0.0.0", port=8000)
