import os
import dotenv
import databento as db
import threading
from collections import deque
from databento_dbn import TradeMsg

dotenv.load_dotenv()
DATABENTO_API_KEY = os.getenv("DATABENTO_API_KEY")


class DataAggregator:
    def __init__(self):
        self.client = db.Live(DATABENTO_API_KEY)

        # Store last 15 minutes of 1s candles
        self.candles = deque(maxlen=900)

        self.current_candle = None

    # -------------------------
    # Candle Helpers
    # -------------------------

    def reset_candle(self, second):
        if self.current_candle is not None:
            with self.app.app_context():
                self.socketio.emit('candle_update', self.current_candle)
        print("Candle updated: ", self.current_candle)
        self.current_candle = {
            "second": second,
            "open": None,
            "high": float("-inf"),
            "low": float("inf"),
            "close": None,
            "buy_vol": 0,
            "sell_vol": 0,
            "delta": 0,
            "price_levels": {}  # price -> [buy_vol, sell_vol]
        }

    def update_candle(self, trade):
        second = trade.ts_event // 1_000_000_000
        price = trade.price  # raw price (integer)
        size = trade.size
        side = 1 if trade.side == "A" else -1

        # First trade initializes candle
        if self.current_candle is None:
            self.reset_candle(second)

        # New second → finalize old candle
        if second > self.current_candle["second"]:
            self.candles.append(self.current_candle)
            self.reset_candle(second)

        c = self.current_candle

        # OHLC
        if c["open"] is None:
            c["open"] = price

        c["high"] = max(c["high"], price)
        c["low"] = min(c["low"], price)
        c["close"] = price

        # Volume / delta
        if side == 1:
            c["buy_vol"] += size
        else:
            c["sell_vol"] += size

        c["delta"] = c["buy_vol"] - c["sell_vol"]

        # Price-level tracking
        levels = c["price_levels"]
        if price not in levels:
            levels[price] = [0, 0]

        if side == 1:
            levels[price][0] += size
        else:
            levels[price][1] += size

    # -------------------------
    # Databento Handlers
    # -------------------------

    def handle_message(self, message):
        if isinstance(message, TradeMsg):
            self.update_candle(message)

    def start(self, app, socketio):
        self.app = app
        self.client.subscribe(
            dataset="GLBX.MDP3",
            schema="trades",
            stype_in="raw_symbol",
            symbols=["ESH6"],
        )
        self.socketio = socketio
        self.client.add_callback(self.handle_message)

        # Non-blocking start in separate thread
        threading.Thread(
            target=self.client.start,
            daemon=True
        ).start()