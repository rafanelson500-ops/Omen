import json
import os
from datetime import datetime, timedelta

import databento as db
import dotenv
import redis
from zoneinfo import ZoneInfo

dotenv.load_dotenv()

DATABENTO_API_KEY = os.getenv("DATABENTO_API_KEY")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# List never expires. Candles older than 1 month are dropped on each update.
OHLCV_RETENTION_SECONDS = 12 * 30 * 24 * 3600  # 1 month

client = db.Historical(DATABENTO_API_KEY)
redis_client = redis.from_url(REDIS_URL)

dataset = "GLBX.MDP3"
# Single key: value is JSON array [{timestamp, open, high, low, close, volume}, ...]. One GET returns the full list.
OHLCV_LIST_KEY = "ohlcv:ES:list"

# Same fixed-point scale as datafeed (prices from API are in 1e-9 units).
PRICE_SCALE = 1_000_000_000


def _parse_ts(ts_str):
    """Parse timestamp string to Unix seconds for retention trim. Matches datafeed."""
    if not ts_str:
        return 0
    try:
        s = str(ts_str).replace("Z", "+00:00").strip()
        dt = datetime.fromisoformat(s)
        return dt.timestamp()
    except Exception:
        return 0


def backfill():
    cst = ZoneInfo("America/Chicago")
    today_cst = datetime.now(cst)

    start_utc = today_cst.astimezone(ZoneInfo("UTC")) - timedelta(days=365)
    end_utc = today_cst.astimezone(ZoneInfo("UTC")) - timedelta(hours=3)

    data = client.timeseries.get_range(
        dataset=dataset,
        schema="ohlcv-1m",
        symbols="ES.v.0",
        stype_in="continuous",
        start=start_utc.strftime("%Y-%m-%d"),
        end=end_utc.strftime("%Y-%m-%dT%H:%M:%S"),
    )

    # Step 2: Build full list in memory (one batch), avoid per-candle Redis round-trips
    backfill_candles = []
    for index, row in data.to_df().iterrows():
        ts = index.isoformat() if hasattr(index, "isoformat") else str(index)
        candle = {
            "timestamp": ts,
            "open": row["open"],
            "high": row["high"],
            "low": row["low"],
            "close": row["close"],
            "volume": int(row["volume"]),
        }
        backfill_candles.append(candle)

    # Step 4: Merge with existing Redis data (don't overwrite newer data from datafeed)
    raw = redis_client.get(OHLCV_LIST_KEY)
    existing = json.loads(raw) if raw else []
    by_ts = {c["timestamp"]: c for c in backfill_candles}
    for c in existing:
        by_ts[c["timestamp"]] = c  # existing (e.g. from datafeed) wins for same ts
    candles = [by_ts[ts] for ts in sorted(by_ts.keys(), key=_parse_ts)]

    # Step 3: Same retention as datafeed: drop candles older than 1 month
    cutoff = datetime.now(ZoneInfo("UTC")).timestamp() - OHLCV_RETENTION_SECONDS
    candles = [c for c in candles if _parse_ts(c.get("timestamp")) >= cutoff]

    redis_client.set(OHLCV_LIST_KEY, json.dumps(candles))


if __name__ == "__main__":
    backfill()