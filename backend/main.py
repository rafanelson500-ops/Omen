import flask
import flask_socketio as socketio
from data import Datastream

app = flask.Flask(__name__)
socketio = socketio.SocketIO(app, cors_allowed_origins="*")

def handle_data(last_id, bids, asks, best_bid, best_ask, spread, ts):
    socketio.emit("chart", {
        "last_id": last_id,
        "bids": bids,
        "asks": asks,
        "best_bid": best_bid,
        "best_ask": best_ask,
        "spread": spread,
        "timestamp": ts
    })

if __name__ == "__main__":
    datastream = Datastream(handle_data)
    datastream.start()

    socketio.run(app, host="0.0.0.0", port=8000, debug=True)