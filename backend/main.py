import os
import dotenv
from data_aggregator import DataAggregator
import time
from flask import Flask
from flask_socketio import SocketIO
from options_handler import OptionsHandler

app = Flask(__name__)
socketio = SocketIO(app)
socketio.init_app(app, cors_allowed_origins="*", async_mode='threading')
dotenv.load_dotenv()


options_handler = OptionsHandler()
data_aggregator = DataAggregator()

@socketio.on('connect')
def handle_connect():
    print('Client connected')
    socketio.emit('hydration_data', data_aggregator.featured_candles.to_dict(orient='records'))
    # emit a list of the string name of all files in ./opens
    socketio.emit('available_data', [f.split(".")[0]+"."+f.split(".")[1] for f in os.listdir("./opens")])

@socketio.on('disconnect')
def handle_disconnect():
    print('Client disconnected')

@socketio.on('message')
def handle_message(msg):
    print(msg)

@socketio.on('mode_change')
def handle_mode_change(mode):
    print(f"Mode changed to {mode}")
    if mode == "live":
        socketio.emit('hydration_data', data_aggregator.featured_candles.to_dict(orient='records'))
    else:
        data = data_aggregator.load_historical_candles(f"./opens/{mode}.csv")
        print(data)
        socketio.emit('hydration_data', data.to_dict(orient='records'))

if __name__ == "__main__":
    data_aggregator.start(app, socketio)
    socketio.run(app, host='0.0.0.0', port=8000, allow_unsafe_werkzeug=True)