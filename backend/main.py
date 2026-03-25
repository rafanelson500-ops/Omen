"""
State machine for trading bot.

Strategy Handler:
    Variables -
        * TP Threshold
        * SL Threshold
        * Pressure Switch Threshold
        * Quality Filter Threshold
        * Trade Cooldown Ticks

    States -
        * Status            IDLE, SETUP_FOUND, IN_TRADE, COOLDOWN
        * Side              LONG, SHORT, NONE
        * Entry Price       Number
        * Daily PnL         Number
        * Trade Count       Number

Regime Handler:
    Variables -
        * Thresholds for regime labels
        * Time windows for session labels

    States -
        * Regime Labels       WARMING_UP, WEAK_TREND, STRONG_TREND, CHOPPY
        * Session             Overnight, Pre-Market, NYSE Open, Lunch, Power Hour
        * Volatility Value    Number

Setup Handler:
    Variables -
        * Thresholds for setup labels

    States -
        * Setup Labels       WARMING_UP, SETUP_FOUND, IN_TRADE, EXIT
        * Absorption Value    Number
        * Pressure Value      Number

Microstate Handler:
    Variables -
        * Thresholds for microstate labels
        * Time windows for microstate labels

    States -
        * Microstate Labels       WARMING_UP, SETUP_FOUND, IN_TRADE, EXIT
        * Pressure Value    Number
        * Absorption Value    Number
        * Volatility Value    Number
"""
from classes.datastream import Datastream
from flask import Flask
from flask_socketio import SocketIO

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

def main():
    datastream = Datastream()

    def on_tick(candle):
        print(1)
        socketio.emit("1-tick", candle)
        # Update strategy state

    def on_10th_tick(candle):
        print(10)
        socketio.emit("10-tick", candle)
        # Update setup state

    def on_100th_tick(candle):
        print(100)
        socketio.emit("100-tick", candle)
        # Update regime state

    datastream.subscribe(1, on_tick)
    datastream.subscribe(10, on_10th_tick)
    datastream.subscribe(100, on_100th_tick)
    datastream.start(simulated=False)


if __name__ == "__main__":
    main()
    socketio.run(app, host="0.0.0.0", port=8000)
