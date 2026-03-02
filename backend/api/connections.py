from flask_socketio import emit

def start_connections(socketio):
    @socketio.on('connect')
    def handle_connect():
        emit('connection_status', True)

    @socketio.on('disconnect')
    def handle_disconnect():
        emit('connection_status', False)