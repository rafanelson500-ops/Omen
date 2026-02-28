import os
import dotenv
import databento as db
import threading
from collections import deque
from databento_dbn import TradeMsg
from feature_engine import FeatureEngine
import pandas as pd
import datetime
from datetime import timedelta
dotenv.load_dotenv()
DATABENTO_API_KEY = os.getenv("DATABENTO_API_KEY")


class DataAggregator:
    def __init__(self):
        self.client = db.Live(DATABENTO_API_KEY)
        self.history_client = db.Historical(DATABENTO_API_KEY)

        # Store last 15 minutes of 1s candles
        self.candles = deque()
        self.featured_candles = pd.DataFrame()
        self.current_candle = None
        self.feature_engine = FeatureEngine()

    # -------------------------
    # Historical Seeding
    # -------------------------

    def load_historical_candles(self, path):
        df = pd.read_csv(path)
        historical_candles = deque()
        # Parse ts_event to integer nanoseconds, then sort chronologically
        df["ts_event_ns"] = (
            pd.to_datetime(df["ts_event"], utc=True).astype("int64")
        )
        df.sort_values("ts_event_ns", inplace=True)

        # CSV prices are floats (e.g. 6855.75); scale to match live TradeMsg.price
        # which is a fixed-point integer (price × 10⁹)
        df["price_int"] = (df["price"] * 1_000_000_000).round().astype("int64")
        df["second"] = df["ts_event_ns"] // 1_000_000_000

        candle = None
        current_second = None

        for row in df.itertuples(index=False):
            second = row.second
            price  = row.price_int
            size   = int(row.size)
            side   = 1 if row.side == "A" else -1

            # New second → finalise previous candle
            if second != current_second:
                if candle is not None:
                    historical_candles.append(candle)
                candle = {
                    "second":       second,
                    "open":         None,
                    "high":         float("-inf"),
                    "low":          float("inf"),
                    "close":        None,
                    "buy_vol":      0,
                    "sell_vol":     0,
                    "delta":        0,
                    "price_levels": {},
                }
                current_second = second

            # OHLC
            if candle["open"] is None:
                candle["open"] = price
            candle["high"]  = max(candle["high"], price)
            candle["low"]   = min(candle["low"],  price)
            candle["close"] = price

            # Volume / delta
            if side == 1:
                candle["buy_vol"] += size
            else:
                candle["sell_vol"] += size
            candle["delta"] = candle["buy_vol"] - candle["sell_vol"]

            # Price-level tracking
            levels = candle["price_levels"]
            if price not in levels:
                levels[price] = [0, 0]
            levels[price][0 if side == 1 else 1] += size

        # Append the final in-progress candle
        if candle is not None:
            historical_candles.append(candle)

        if historical_candles:
            return self.feature_engine.featurize_candles(historical_candles)

    # -------------------------
    # Candle Helpers
    # -------------------------

    def reset_candle(self, second):
        if self.current_candle is not None:
            with self.app.app_context():
                self.socketio.emit('candle_update', self.featured_candles.iloc[-1].to_dict())
                print("Candle updated: ", self.featured_candles.iloc[-1].to_dict())
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
            self.featured_candles = self.feature_engine.featurize_candles(self.candles)
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