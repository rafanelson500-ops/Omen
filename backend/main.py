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
        * Status            IDLE, IN_TRADE, COOLDOWN
        * Side              LONG, SHORT, NONE
        * Entry Price       Number
        * Daily PnL         Number
        * Trade Count       Number

    Flow -
        IDLE -> IN_TRADE -> COOLDOWN -> IDLE

    Methods -
        submit_trade(): checks if trade doesnt violate any risk params/cooldowns

Regime Handler:
    Variables -
        * Thresholds for regime labels
        * Definitions for session labels

    States -
        * Regime Labels       WARMING_UP, WEAK_TREND, STRONG_TREND, CHOPPY
        * Session             Overnight, Pre-Market, NYSE Open, Lunch, Power Hour
        * Volatility Value    Number

    Methods -
        update_regime(): callback for 100th tick, updates regime labels, session, and volatility

Setup Handler:
    Variables -
        * Thresholds for setup labels

    States -
        * Setup Labels        WARMING_UP, NO_SETUP, LONG_SETUP, SHORT_SETUP
        * Pressure Value      Number
        * Delta               Number

    Methods -
        update_setup(): callback for 10th tick, updates setup labels, pressure, and delta

Microstate Handler:
    Variables -
        * Thresholds for microstate labels
        * Time windows for microstate labels

    States -
        * Absorption Value    Number
        * Ticks per second    Number

    Methods -
        update_microstate(): callback for every tick, updates absorption, and tps
        handle_signal(): checks for alignment on every layer, then submits the trade

Pipeline:
    Every 100 ticks       Update regime states
    Every 10 ticks        Update setups
    Every 1 tick          Check for trigger

    If trigger:
        check if regime is tradeable else 'Blocked by regime'
        check if trigger aligns with setup else pass
        check if setup is quality enough else 'Blocked by quality filter
        check if not in trade else 'Blocked by ongoing trade'
        place trade with quality based risk settings (5% on medium conviction, 10% on high conviction)

"""
from classes.datastream import Datastream
from classes.microstate import Microstate
from flask import Flask
from flask_socketio import SocketIO

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

def main():
    datastream = Datastream()
    microstate = Microstate()

    def on_tick(candle):
        microstate.update(candle)
        # socketio.emit("1-tick", candle)

    def on_10th_tick(candle):
        pass
        # print(10)
        # socketio.emit("10-tick", candle)
        # Update setup state

    def on_100th_tick(candle):
        pass
        # print(100)
        # socketio.emit("100-tick", candle)
        # Update regime state

    datastream.subscribe(1, on_tick)
    datastream.subscribe(10, on_10th_tick)
    datastream.subscribe(100, on_100th_tick)
    datastream.start(simulated=False)


if __name__ == "__main__":
    main()
    socketio.run(app, host="0.0.0.0", port=8000)
