from .connections import start_connections
from .agentic_strategy import start_agentic_strategy
from .model_lab import start_model_lab
def start_api(socketio):
    start_connections(socketio)
    start_agentic_strategy(socketio)
    start_model_lab(socketio)