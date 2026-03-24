from engine_datastream import DatastreamEngine
from engine_microstate import MicrostateEngine
from engine_regime import RegimeFilter
from engine_setup import SetupDetector
from engine_strategy import StrategyEngine
from flask import Flask
from flask_socketio import SocketIO

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")


def main():
    datastream = DatastreamEngine()
    micro_engine = MicrostateEngine(window=40)
    regime_engine = RegimeFilter(window=20)
    setup_engine = SetupDetector(window=24)
    strategy_engine = StrategyEngine()

    latest_micro = {"pressure": 0.0, "absorption": 0.0, "volatility": 0.0}
    latest_regime: dict[str, object] = {
        "tradable": False,
        "type": "chop",
        "volatility": "low",
        "reasons": ["warming_up"],
    }

    def emit_events(events):
        for event_name, payload in events:
            socketio.emit(event_name, payload)

    def on_tick(candle):
        socketio.emit("1-tick", candle)
        events = strategy_engine.on_tick(candle, latest_micro)
        emit_events(events)

    def on_10th_tick(candle):
        socketio.emit("10-tick", candle)
        nonlocal latest_micro, latest_regime
        # Pressure/absorption are evaluated on 10-tick bars.
        latest_micro = micro_engine.update(candle)
        # Regime inference is also evaluated on 10-tick bars.
        latest_regime = regime_engine.update(candle)
        emit_events(strategy_engine.on_regime(latest_regime, ts=float(candle["time"])))

    def on_100th_tick(candle):
        socketio.emit("100-tick", candle)
        # Trade discovery happens on 100-tick bars; 1-tick is only for fills/exits.
        setup = setup_engine.update(candle, latest_micro, latest_regime)
        events = strategy_engine.on_setup(
            setup=setup,
            ts=float(candle["time"]),
            signal_price=float(candle["close"]),
        )
        emit_events(events)

    datastream.subscribe(1, on_tick)
    datastream.subscribe(10, on_10th_tick)
    datastream.subscribe(100, on_100th_tick)
    datastream.start(simulated=True, speed=1)


if __name__ == "__main__":
    main()
    socketio.run(app, host="0.0.0.0", port=8000)
