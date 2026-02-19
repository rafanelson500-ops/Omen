from flask import Flask, jsonify
from flask_cors import CORS
from flask_socketio import SocketIO, emit
from helpers.config_handler import load_setting, set_setting, load_config
from helpers.bot_handler import set_bot_enabled, get_bot_enabled, set_lots_size, set_session
from helpers.logs import get_logs
from helpers.data_handler import get_data
from bot.run import get_enriched_data, loop
import threading
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app, cors_allowed_origins="*")
CORS(app, origins="*")

actions = {
    "set_bot_enabled": set_bot_enabled,
    "get_bot_enabled": get_bot_enabled,
    "set_session": set_session,
    "get_all": load_config,
    "set_lots_size": set_lots_size,
    "get_data": get_data,
    "get_enriched_data": get_enriched_data,
    "get_logs": get_logs,
}

@app.route('/health')
def health():
    return "OK"

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
    # Listen on all interfaces (0.0.0.0) to allow external access
    if os.environ.get('WERKZEUG_RUN_MAIN') != 'true':
        # This is the reloader process, skip thread creation
        pass
    else:
        # This is the main process
        thread = threading.Thread(target=loop)
        thread.daemon = True
        thread.start()
    socketio.run(app, debug=True, host='0.0.0.0', port=8000)

