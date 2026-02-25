import json
import os
import time
import threading
from datetime import datetime, timezone
from pathlib import Path

import databento as db
import dotenv
import redis

dotenv.load_dotenv()

DATABENTO_API_KEY = os.getenv("DATABENTO_API_KEY")

dataset = "GLBX.MDP3"

# Global state
client = db.Historical(DATABENTO_API_KEY)

data = client.timeseries.get_range(
    dataset="OPRA.PILLAR",
    schema="definition",       # or "trades", "mbp-1" for quotes, "ohlcv-1m", etc.
    symbols="SPX.OPT",         # parent symbol — returns all SPX option contracts
    stype_in="parent",         # use "parent" to get all contracts under SPX
    start="2026-02-24",
    end="2026-02-25",
)

# Convert to DataFrame
df = data.to_df()

print(df[["raw_symbol", "strike_price", "expiration"]])