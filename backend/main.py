import csv
import glob
import json
import os
from typing import Literal, TypedDict

from database import datafeed
from database.datafeed import start as start_datafeed
from flask import Flask, jsonify
from flask_socketio import SocketIO

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")


def handle_new_1s_candle(candle: dict):
    print("1s", candle)

def handle_new_1m_candle(candle: dict):
    print("1m", candle)

def handle_new_15m_candle(candle: dict):
    print("15m", candle)

def main():
    start_datafeed({"1s": handle_new_1s_candle, "1m": handle_new_1m_candle, "15m": handle_new_15m_candle})


if __name__ == "__main__":
    print("Starting pipeline")
    main()
    socketio.run(app, host="0.0.0.0", port=8000)
