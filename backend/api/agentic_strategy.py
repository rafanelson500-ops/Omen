from agentic_strategy.main import get_result
from flask_socketio import emit
from flask import request

def start_agentic_strategy(socketio):
    @socketio.on('run_agentic_strategy')
    def handle_agentic_strategy(data):
        sid = request.sid

        def on_task_complete(task_output):
            socketio.emit('agent_report', {
                'agent': task_output.agent,
                'report': task_output.raw,
            }, room=sid)

        try:
            result = get_result(on_task_complete=on_task_complete)
            emit('run_agentic_strategy', result.raw)
        except Exception as e:
            emit('run_agentic_strategy', "error: " + str(e))