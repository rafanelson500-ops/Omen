from flask import Flask, jsonify
from flask_cors import CORS
from flask_socketio import SocketIO, emit
from helpers.config_handler import load_setting, set_setting, load_config
from helpers.bot_handler import set_bot_enabled, get_bot_enabled, set_lots_size

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app, cors_allowed_origins="*")
CORS(app, origins="*")

actions = {
    "set_bot_enabled": set_bot_enabled,
    "get_bot_enabled": get_bot_enabled,
    "get_all": load_config,
    "set_lots_size": set_lots_size,
}

@socketio.on('connect')
def handle_connect():
    print('Client connected')
    emit('message', {'data': 'Connected to server', 'id': 0})

@socketio.on('message')
def handle_message(data):
    print("Message received: ", data)
    if 'action' in data:
        if data['action'] in actions:
            response = None
            if "data" in data:
                response = actions[data['action']](data['data'])
            else:
                response = actions[data['action']]()
            if 'id' in data:
                emit('message', {'data': response, 'id': data['id']})
        else:
            print("Unknown action: ", data['action'])
    else:
        print("Unknown message received: ", data)

if __name__ == '__main__':
    socketio.run(app, debug=True)

