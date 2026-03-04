import time
from datetime import datetime, timezone
from agentic_strategy.main import get_result
from dotenv import load_dotenv
import os
import requests
import json
load_dotenv()

webhook_url = os.getenv("WEBHOOK_URL")
if not webhook_url:
    raise ValueError("WEBHOOK_URL is not set")

execution_times = [
    "16:00:00",
    "17:15:00",
    "18:30:00",
    "20:00:00"
]

def start_engine():
    while True:
        current_time = datetime.now(timezone.utc).strftime("%H:%M:%S")
        if current_time in execution_times:
            result = get_result()
            result_str = result.raw.strip()
            
            # Skip if result is "PASS" (no trade)
            if result_str == "PASS":
                print(f"{current_time} - No trade signal (PASS)")
                time.sleep(1)
                continue
            
            # Parse the result string (it's a Python dict string, need to convert to JSON)
            try:
                # Convert Python dict string (single quotes) to JSON (double quotes)
                json_str = result_str.replace("'", '"')
                data = json.loads(json_str)
                
                # Extract trade parameters
                side = data.get("side", "").upper()
                entry_limit = data.get("entry_limit")
                size = data.get("size")
                stop_loss = data.get("stop_loss")
                take_profit = data.get("take_profit")
                
                # Validate required fields
                if not all([side, entry_limit is not None, size, stop_loss is not None, take_profit is not None]):
                    print(f"{current_time} - Invalid trade signal: missing required fields")
                    time.sleep(1)
                    continue
                
                # Convert BUY/SELL to lowercase for TradersPost
                action = side.lower()
                
                # Build TradersPost webhook body (always use limit orders)
                body = {
                    "ticker": "ES",
                    "action": action,
                    "orderType": "limit",
                    "limitPrice": entry_limit,
                    "quantity": int(size),
                    "takeProfit": {
                        "limitPrice": take_profit
                    },
                    "stopLoss": {
                        "type": "stop",
                        "stopPrice": stop_loss
                    }
                }
                
                # Send webhook to TradersPost
                try:
                    response = requests.post(webhook_url, json=body, timeout=10)
                    response.raise_for_status()
                    print(f"{current_time} - Trade signal sent: {side} {size} @ {entry_limit}, SL: {stop_loss}, TP: {take_profit}")
                except requests.exceptions.RequestException as e:
                    print(f"{current_time} - Error sending webhook: {e}")
                    
            except (json.JSONDecodeError, KeyError, ValueError) as e:
                print(f"{current_time} - Error parsing trade signal: {e}")
                print(f"Raw result: {result_str}")

        time.sleep(1)