import pandas as pd
import flask
import flask_socketio as socketio
import utils.data as data

df = data.get_data()
print(df.head(50))

# app = flask.Flask(__name__)
# socketio = socketio.SocketIO(app)

# if __name__ == "__main__":
#     socketio.run(app, host="0.0.0.0", port=8000)