import json
import time
import websocket
import threading
import datetime
from typing import Callable

class Datastream:
    def __init__(self, callback: Callable):
        self.ws = websocket.WebSocketApp(
            f"wss://stream.binance.us:9443/ws/btcusdt@aggTrade",
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close,
            on_open=self.on_open,
        )
        self.callback = callback

    def start(self):
        t = threading.Thread(target=self.ws.run_forever)
        t.daemon = True
        t.start()

    def on_message(self, ws, message):
        data = json.loads(message)
        print(data)
        ts = datetime.datetime.now(datetime.timezone.utc).timestamp()
        #self.callback(last_id, bids, asks, best_bid, best_ask, spread, ts)

    def on_close(self, ws, code, msg):
        print(f"Closed: code={code} msg={msg}")

    def on_error(self, ws, error):
        print(f"Error: {error}")

    def on_open(self, ws):
        print(f"Connected to Binance")