import csv
import glob
import json
import os
from typing import Literal, TypedDict

from database import datafeed
from database.datafeed import start as start_datafeed
from flask import Flask, jsonify
from flask_socketio import SocketIO

from signal_engine import SignalEngine

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")


def handle_new_1s_candle(candle: dict):
    print("1s", candle)

def handle_new_1m_candle(candle: dict):
    print("1m", candle)

def handle_new_5m_candle(candle: dict):
    print("5m", candle)

def main():
    signal_engine = SignalEngine()
    start_datafeed({"1s": signal_engine.on_1s, "1m": signal_engine.on_1m, "5m": signal_engine.on_5m}, signal_engine.on_tick)


if __name__ == "__main__":
    print("Starting pipeline")
    main()
    socketio.run(app, host="0.0.0.0", port=8000)
