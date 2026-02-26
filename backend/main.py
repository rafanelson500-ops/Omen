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

@socketio.on('connect')
def handle_connect():
    print('Client connected')

@socketio.on('disconnect')
def handle_disconnect():
    print('Client disconnected')

@socketio.on('message')
def handle_message(msg):
    print(msg)

if __name__ == "__main__":
    options_handler = OptionsHandler()
    options_handler.get_options()
    # data_aggregator = DataAggregator()
    # data_aggregator.start(app, socketio)
    # socketio.run(app, host='0.0.0.0', port=8000, allow_unsafe_werkzeug=True)