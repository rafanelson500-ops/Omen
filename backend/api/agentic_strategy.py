from agentic_strategy.main import get_result
from flask_socketio import emit
from flask import request

running = False

def start_agentic_strategy(socketio):
    @socketio.on('run_agentic_strategy')
    def handle_agentic_strategy(data):
        global running
        if running: return

        def on_task_complete(task_output):
            socketio.emit('agent_report', {
                'agent': task_output.agent,
                'report': task_output.raw,
            })

        running = True
        result = get_result(on_task_complete=on_task_complete)
        socketio.emit('agent_final', result.raw)
        running = False