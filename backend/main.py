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
import math

from classes.datastream import Datastream
from classes.microstate import Microstate
from classes.regime import Regime
from classes.strategy import Strategy
from classes.setup import Setup
from classes.trigger import Trigger
from flask import Flask
from flask_socketio import SocketIO

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

def main():
    # Simulated + instant: no wall-clock sleep, one WebSocket payload when the run finishes (good for backtests).
    # Simulated + not instant: historical spacing via sleep, per-tick emits (live-style chart).
    SIMULATED = True
    INSTANT_REPLAY = True
    BATCH_MODE = SIMULATED and INSTANT_REPLAY

    batch_ticks: list = []
    batch_10: list = []
    batch_100: list = []
    batch_strategy_status: list = []
    last_instant_payload: dict | None = None

    def emit_confluence(confluence):
        trigger.on_confluence(confluence)
        if not BATCH_MODE:
            socketio.emit("confluence", {"recent": list(setup.confluences)})

    datastream = Datastream()
    strategy = Strategy()
    regime = Regime()
    setup = Setup(on_confluence=emit_confluence)
    microstate = Microstate(setup.push_signal)
    trigger = Trigger(microstate, setup, regime, strategy)
    last_status = strategy.status

    @socketio.on("connect")
    def on_connect():
        socketio.emit("confluence", {"recent": list(setup.confluences)})

    @socketio.on("request_instant_snapshot")
    def on_request_instant_snapshot():
        if last_instant_payload is not None:
            socketio.emit("instant_backtest", last_instant_payload)

    def on_tick(candle):
        nonlocal last_status
        microstate.update(candle)
        strategy.on_tick(candle)
        trigger.on_tick(candle)
        strategy_block = {
            "status": strategy.status,
            "side": strategy.side,
            "position_size": strategy.position_size,
            "pnl": strategy.pnl,
            "entry_price": strategy.entry_price,
            "commission": strategy.commission,
            "trade_count": strategy.trade_count,
            "cooldown_ticks": strategy.cooldown_ticks,
            "balance": strategy.balance,
            "ruin_level": strategy.ruin_level,
            "account_blown": strategy.ACCOUNT_BLOWN,
        }
        payload = {
            "tick": {
                "time": candle["time"],
                "value": candle["close"],
            },
            "microstate": {
                "tps": microstate.tps[-1] if len(microstate.tps) > 0 else 0,
                "average_tps": microstate.average_tps,
                "aggression_efficiency": microstate.aggression_efficiency[-1]
                if len(microstate.aggression_efficiency) > 0
                else 0,
            },
            "strategy": strategy_block,
        }
        if BATCH_MODE:
            batch_ticks.append(payload)
        else:
            socketio.emit("tick", payload)
        if strategy.status != last_status:
            last_status = strategy.status
            status_msg = {**strategy_block, "time": candle["time"]}
            if BATCH_MODE:
                batch_strategy_status.append(status_msg)
            else:
                socketio.emit("strategy_status", status_msg)

    def on_10th_tick(candle):
        setup.on_10th_tick(candle)
        msg_10 = {
            **candle,
            "bar_delta": setup.bar_delta,
            "avg_delta": setup.avg_delta,
        }
        if BATCH_MODE:
            batch_10.append(msg_10)
        else:
            socketio.emit("10-tick", msg_10)

    def on_100th_tick(candle):
        regime.on_100th_tick(candle)
        eff = regime.regime_efficiency
        msg_100 = {
            "c": candle,
            "vwap": regime.vwap[-1],
            "vwap_sigma": regime.vwap_std[-1] if len(regime.vwap_std) > 0 else 0,
            "regime": {
                "label": regime.regime_label,
                "efficiency": float(eff) if isinstance(eff, float) and math.isfinite(eff) else None,
                "flips": regime.regime_flips,
            },
        }
        if BATCH_MODE:
            batch_100.append(msg_100)
        else:
            socketio.emit("100-tick", msg_100)

    def on_instant_backtest_complete() -> None:
        nonlocal last_instant_payload
        last_instant_payload = {
            "ticks": batch_ticks,
            "ten_ticks": batch_10,
            "hundred_ticks": batch_100,
            "strategy_statuses": batch_strategy_status,
            "confluence": {"recent": list(setup.confluences)},
        }
        socketio.emit("instant_backtest", last_instant_payload)

    datastream.subscribe(1, on_tick)
    datastream.subscribe(10, on_10th_tick)
    datastream.subscribe(100, on_100th_tick)
    datastream.start(
        simulated=SIMULATED,
        instant=INSTANT_REPLAY,
        on_complete=on_instant_backtest_complete if BATCH_MODE else None,
    )

if __name__ == "__main__":
    main()
    socketio.run(app, host="0.0.0.0", port=8000)
