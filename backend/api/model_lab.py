from flask_socketio import emit
from helpers.data import get_data

def start_model_lab(socketio):
    @socketio.on('load_data')
    def load_data():
        df = get_data()
        df = add_features(df)
        emit('load_data', df.to_dict(orient='records'))
