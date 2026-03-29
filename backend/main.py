from flask import Flask, jsonify
from flask_socketio import SocketIO, emit

from classes.datastream import Datastream
from classes.features import add_tick_features

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

@socketio.on('connect')
def handle_connect():
    print('Client connected')
    emit('connected')

@socketio.on('disconnect')
def handle_disconnect():
    print('Client disconnected')
    emit('disconnected')

@socketio.on('backtest')
def handle_backtest(date):
    print(f'Backtesting on {date}')
    backtest(date+"T14:29:00.000000000Z", date+"T15:30:00.000000000Z")

def backtest(start_date, end_date):
    datastream = Datastream()
    short_df, medium_df, long_df = datastream.historical(start_date, end_date)
    short_df = add_tick_features(short_df)

    short_df.dropna(inplace=True)
    medium_df.dropna(inplace=True)
    long_df.dropna(inplace=True)

    # Nanosecond unix times (~1e18) lose precision in JSON → Number in the browser;
    # distinct rows can become equal times and break lightweight-charts (strictly
    # increasing). Microseconds fit in JS integer-safe range; then dedupe + sort.
    short_df = short_df.copy()
    short_df["time"] = (short_df["time"] // 1_000_000).astype("int64")
    short_df = short_df.sort_values("time").drop_duplicates(subset=["time"], keep="last")

    socketio.emit('backtest', {
        "tick": short_df.to_dict(orient="records")
    })

if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=8000)