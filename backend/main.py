from engine_datastream import DatastreamEngine
import time
from flask import Flask, jsonify
from flask_socketio import SocketIO
from datetime import datetime

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

def on_tick(tick):
    print(tick["price"])
    socketio.emit('tick', tick)

def main():
    datastream = DatastreamEngine()
    datastream.start_simulated()
    datastream.subscribe(on_tick)

if __name__ == "__main__":
    main()
    socketio.run(app, host='0.0.0.0', port=8000)