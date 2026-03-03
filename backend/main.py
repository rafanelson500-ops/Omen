import os
from dotenv import load_dotenv
from flask import Flask, request, jsonify
from flask_socketio import SocketIO, emit
from api.main import start_api
from engine.main import start_engine

load_dotenv()

app = Flask(__name__)
socketio = SocketIO(app)
socketio.init_app(app, cors_allowed_origins="*")

start_api(socketio)

start_engine()

# if __name__ == "__main__":
#     socketio.run(app, debug=True, port=8000, host='0.0.0.0')