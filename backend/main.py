import threading

from flask import Flask
from flask_socketio import SocketIO, emit
import pandas as pd
from classes.datastream import Datastream
from classes.features import add_tick_features, add_context_features, microstate_features

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")


def _filter_rth_utc(df: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    """Keep rows whose ``time`` column (Unix seconds) falls in [start, end] UTC time-of-day."""
    if df.empty or "time" not in df.columns:
        return df
    idx = pd.DatetimeIndex(pd.to_datetime(df["time"], unit="s", utc=True))
    loc = idx.indexer_between_time(start, end, include_start=True, include_end=True)
    return df.iloc[loc].copy()


def _emit_from_live(event: str, payload: dict) -> None:
    """Broadcast from Databento thread (Flask-SocketIO threading mode)."""
    with app.app_context():
        socketio.emit(event, payload, namespace="/")


@socketio.on("connect")
def handle_connect():
    print("Client connected")
    emit("connected")


@socketio.on("disconnect")
def handle_disconnect():
    print("Client disconnected")
    emit("disconnected")


@socketio.on("backtest")
def handle_backtest(date):
    print(f"Backtesting on {date}")
    backtest(date + "T14:25:00.000000000Z", date + "T15:00:00.000000000Z")


def backtest(start_date, end_date):
    datastream = Datastream()
    short_df, medium_df, long_df = datastream.historical(start_date, end_date)
    short_df = add_tick_features(short_df)
    medium_df = microstate_features(medium_df)
    long_df = add_context_features(long_df)

    short_df = _filter_rth_utc(short_df, "14:30:00", "15:00:00")
    medium_df = _filter_rth_utc(medium_df, "14:30:00", "15:00:00")
    long_df = _filter_rth_utc(long_df, "14:30:00", "15:00:00")

    short_df.dropna(inplace=True)
    medium_df.dropna(inplace=True)
    long_df.dropna(inplace=True)

    socketio.emit(
        "backtest",
        {
            "tick": short_df.to_dict(orient="records"),
            "10-tick": medium_df.to_dict(orient="records"),
            "100-tick": long_df.to_dict(orient="records"),
        },
    )


def start_live_stream() -> None:
    """Run Databento live client in a daemon thread so the HTTP server can bind."""

    short_df = pd.DataFrame()
    medium_df = pd.DataFrame()
    long_df = pd.DataFrame()

    def on_tick(row: dict) -> None:
        nonlocal short_df
        short_df = pd.concat([short_df, pd.DataFrame([row])], ignore_index=True)
        short_df = add_tick_features(short_df)
        _emit_from_live("tick", short_df.iloc[-1].to_dict())

    def on_medium(row: dict) -> None:
        nonlocal medium_df
        medium_df = pd.concat([medium_df, pd.DataFrame([row])], ignore_index=True)
        _emit_from_live("10-tick", medium_df.iloc[-1].to_dict())

    def on_long(row: dict) -> None:
        nonlocal long_df
        long_df = pd.concat([long_df, pd.DataFrame([row])], ignore_index=True)
        _emit_from_live("100-tick", long_df.iloc[-1].to_dict())

    stream = Datastream(on_tick, on_medium, on_long)

    def run() -> None:
        try:
            stream.live()
        except Exception as exc:
            print(f"Live stream ended: {exc!r}")

    threading.Thread(target=run, name="databento-live", daemon=True).start()


if __name__ == "__main__":
    #start_live_stream()
    socketio.run(app, host="0.0.0.0", port=8000)
