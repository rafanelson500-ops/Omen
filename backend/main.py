import os
from dotenv import load_dotenv
from flask import Flask, request, jsonify
from flask_socketio import SocketIO, emit
from api.main import start_api
from engine.main import start_engine
import threading

load_dotenv()

app = Flask(__name__)
socketio = SocketIO(app)
socketio.init_app(app, cors_allowed_origins="*")

start_api(socketio)

if __name__ == "__main__":
    thread = threading.Thread(target=start_engine, daemon=True)
    thread.start()
    socketio.run(app, debug=True, port=8000, host='0.0.0.0')