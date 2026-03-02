from .connections import start_connections
from .agentic_strategy import start_agentic_strategy
def start_api(socketio):
    start_connections(socketio)
    start_agentic_strategy(socketio)