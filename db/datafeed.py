import json
import os
import time
from datetime import datetime

import databento as db
import dotenv
import redis

dotenv.load_dotenv()

DATABENTO_API_KEY = os.getenv("DATABENTO_API_KEY")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# List never expires. Candles older than 1 month are dropped on each update.
OHLCV_RETENTION_SECONDS = 30 * 24 * 3600  # 1 month

client = db.Live(DATABENTO_API_KEY)
redis_client = redis.from_url(REDIS_URL)

dataset = "GLBX.MDP3"
# Single key: value is JSON array [{timestamp, open, high, low, close, volume}, ...]. One GET returns the full list.
OHLCV_LIST_KEY = "ohlcv:ES:list"


def handle_data(data):
    if str(type(data)) == "<class 'databento_dbn.OHLCVMsg'>":
        timestamp = data.pretty_ts_event
        open_ = data.open / 1000000000
        high = data.high / 1000000000
        low = data.low / 1000000000
        close = data.close / 1000000000
        volume = data.volume
        print(f"Timestamp: {timestamp}, Open: {open_}, High: {high}, Low: {low}, Close: {close}, Volume: {volume}")

        candle = {
            "timestamp": str(timestamp),
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        }

        raw = redis_client.get(OHLCV_LIST_KEY)
        candles = json.loads(raw) if raw else []
        candles.append(candle)
        cutoff = time.time() - OHLCV_RETENTION_SECONDS
        candles = [c for c in candles if _parse_ts(c.get("timestamp")) >= cutoff]
        redis_client.set(OHLCV_LIST_KEY, json.dumps(candles))


def _parse_ts(ts_str):
    """Parse timestamp string to Unix seconds for retention trim."""
    if not ts_str:
        return 0
    try:
        s = str(ts_str).replace("Z", "+00:00").strip()
        dt = datetime.fromisoformat(s)
        return dt.timestamp()
    except Exception:
        return 0


client.subscribe(
    dataset = dataset,
    schema = "ohlcv-1m",
    symbols = "ES.v.0",
    stype_in = "continuous",
)

client.add_callback(handle_data)

client.start()

while True:
    time.sleep(1)