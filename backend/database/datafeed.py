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

# Dedicated log file for datafeed (separate from main logs)
LOG_FILE = Path(__file__).parent / "datafeed.log"
_log_lock = threading.Lock()


def log(message):
    """Thread-safe logging to dedicated datafeed log file."""
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"{timestamp} - {message}\n"
    
    with _log_lock:
        try:
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(log_entry)
        except Exception as e:
            # Fallback to print if file write fails
            print(f"[{timestamp}] {message}")
            print(f"Log write error: {e}")


DATABENTO_API_KEY = os.getenv("DATABENTO_API_KEY")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# List never expires. Candles older than 1 month are dropped on each update.
OHLCV_RETENTION_SECONDS = 30 * 24 * 3600  # 1 month

dataset = "GLBX.MDP3"
# Single key: value is JSON array [{timestamp, open, high, low, close, volume}, ...]. One GET returns the full list.
OHLCV_LIST_KEY = "ohlcv:ES:list"

# Global state
client = None
redis_client = None
client_thread = None
running = True
reconnect_delay = 5  # Start with 5 seconds, will use exponential backoff
_connection_lock = threading.Lock()  # Prevent concurrent connection attempts
_connecting = False  # Flag to track if we're currently attempting a connection


def _parse_ts(ts_str):
    """Parse timestamp string to Unix seconds for retention trim."""
    if not ts_str:
        return 0
    try:
        s = str(ts_str).replace("Z", "+00:00").strip()
        dt = datetime.fromisoformat(s)
        return dt.timestamp()
    except Exception as e:
        log(f"Error parsing timestamp '{ts_str}': {e}")
        return 0


def ensure_redis_connection():
    """Ensure Redis connection is active, reconnect if needed."""
    global redis_client
    max_retries = 3
    retry_delay = 1
    
    for attempt in range(max_retries):
        try:
            if redis_client is None:
                log("Connecting to Redis...")
                redis_client = redis.from_url(REDIS_URL, socket_connect_timeout=5, socket_timeout=5)
            
            # Test connection
            redis_client.ping()
            return True
        except (redis.ConnectionError, redis.TimeoutError, Exception) as e:
            log(f"Redis connection error (attempt {attempt + 1}/{max_retries}): {e}")
            redis_client = None
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
                retry_delay *= 2
            else:
                log("Failed to connect to Redis after all retries")
                return False
    return False


def handle_data(data):
    """Handle incoming data from Databento with comprehensive error handling."""
    global redis_client
    try:
        if str(type(data)) == "<class 'databento_dbn.OHLCVMsg'>":
            timestamp = data.pretty_ts_event
            open_ = data.open / 1000000000
            high = data.high / 1000000000
            low = data.low / 1000000000
            close = data.close / 1000000000
            volume = data.volume
            log(f"Received data - Timestamp: {timestamp}, Open: {open_}, High: {high}, Low: {low}, Close: {close}, Volume: {volume}")

            candle = {
                "timestamp": str(timestamp),
                "open": open_,
                "high": high,
                "low": low,
                "close": close,
                "volume": volume,
            }

            # Ensure Redis connection before writing
            if not ensure_redis_connection():
                log("Skipping Redis write - connection unavailable")
                return

            try:
                # Get existing candles
                raw = redis_client.get(OHLCV_LIST_KEY)
                candles = json.loads(raw) if raw else []
                
                # Add new candle
                candles.append(candle)
                
                # Trim old candles
                cutoff = time.time() - OHLCV_RETENTION_SECONDS
                candles = [c for c in candles if _parse_ts(c.get("timestamp")) >= cutoff]
                
                # Write back to Redis
                redis_client.set(OHLCV_LIST_KEY, json.dumps(candles))
                log(f"Successfully updated Redis with {len(candles)} candles")
            except (redis.ConnectionError, redis.TimeoutError) as e:
                log(f"Redis error during write: {e}. Will retry on next data.")
                redis_client = None  # Force reconnection next time
            except json.JSONDecodeError as e:
                log(f"JSON decode error: {e}. Resetting Redis key.")
                try:
                    redis_client.set(OHLCV_LIST_KEY, json.dumps([candle]))
                except Exception as e2:
                    log(f"Failed to reset Redis key: {e2}")
            except Exception as e:
                log(f"Unexpected error handling data: {e}")
    except Exception as e:
        log(f"Critical error in handle_data: {e}")


def is_client_connected():
    """Check if client exists and is connected."""
    global client
    if client is None:
        return False
    try:
        return client.is_connected()
    except Exception:
        return False


def connect_and_start():
    """Connect to Databento and start the client in a blocking manner."""
    global client, reconnect_delay, _connecting
    
    while running:
        # Check if already connected before attempting connection
        if is_client_connected():
            log("Client already connected, waiting...")
            time.sleep(30)
            continue
        
        # Use lock to prevent concurrent connection attempts
        with _connection_lock:
            # Double-check after acquiring lock
            if is_client_connected():
                log("Client connected by another thread, skipping...")
                time.sleep(30)
                continue
            
            if _connecting:
                log("Connection attempt already in progress, skipping...")
                time.sleep(30)
                continue
            
            _connecting = True
        
        try:
            log("Connecting to Databento...")
            
            if not DATABENTO_API_KEY:
                log("ERROR: DATABENTO_API_KEY not set. Waiting before retry...")
                time.sleep(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 2, 300)  # Max 5 minutes
                _connecting = False
                continue
            
            # Create new client
            client = db.Live(DATABENTO_API_KEY)
            
            # Subscribe
            try:
                client.subscribe(
                    dataset=dataset,
                    schema="ohlcv-1m",
                    symbols="ES.v.0",
                    stype_in="continuous",
                )
                client.add_callback(handle_data)
                
                log("Successfully subscribed. Starting client...")
                reconnect_delay = 5  # Reset delay on successful connection
                _connecting = False  # Connection established
                
                # This is blocking - will run until connection fails
                client.start()
                
            except Exception as e:
                log(f"Error during subscription or start: {e}")
                client = None
                _connecting = False
                raise
            
        except KeyboardInterrupt:
            log("Received keyboard interrupt, shutting down...")
            _connecting = False
            break
        except Exception as e:
            log(f"Databento connection error: {e}")
            client = None
            _connecting = False
            
            # Exponential backoff with max delay
            log(f"Waiting {reconnect_delay} seconds before reconnecting...")
            time.sleep(reconnect_delay)
            reconnect_delay = min(reconnect_delay * 2, 300)  # Max 5 minutes


def monitor_connection():
    """Monitor the connection and restart if needed."""
    global client, client_thread, reconnect_delay, _connecting
    
    while running:
        try:
            time.sleep(30)  # Check every 30 seconds
            
            # Check if client is actually connected
            is_connected = is_client_connected()
            
            # Check if client thread is alive
            thread_alive = client_thread is not None and client_thread.is_alive()
            
            # Only restart if:
            # 1. Thread is not alive AND we're not already connecting AND not connected
            # 2. OR client exists but reports disconnected AND we're not already connecting
            if not is_connected and not _connecting:
                if not thread_alive:
                    log("Client thread is not alive and not connected. Restarting...")
                    reconnect_delay = 5  # Reset delay
                    with _connection_lock:
                        if not _connecting and not is_client_connected():
                            client_thread = threading.Thread(target=connect_and_start, daemon=True)
                            client_thread.start()
                elif client is not None:
                    log("Client reports disconnected. Will restart on next check...")
                    # Don't restart immediately, let the connect_and_start loop handle it
            
            # Test Redis connection periodically
            if not ensure_redis_connection():
                log("Redis connection lost. Will retry on next data write.")
            
        except Exception as e:
            log(f"Error in monitor thread: {e}")
            time.sleep(10)


def main():
    """Main entry point with proper initialization and cleanup."""
    global client, client_thread, running
    
    log("Starting datafeed script...")
    
    # Initialize Redis connection
    if not ensure_redis_connection():
        log("WARNING: Could not connect to Redis initially. Will retry on first data write.")
    
    # Check if already connected before starting
    if not is_client_connected():
        # Start client in a separate thread (since start() is blocking)
        client_thread = threading.Thread(target=connect_and_start, daemon=True)
        client_thread.start()
    else:
        log("Client already connected, skipping initial connection attempt.")
    
    # Start monitoring thread
    monitor_thread = threading.Thread(target=monitor_connection, daemon=True)
    monitor_thread.start()
    
    try:
        # Keep main thread alive
        while running:
            time.sleep(1)
    except KeyboardInterrupt:
        log("Received keyboard interrupt, shutting down...")
        running = False
    except Exception as e:
        log(f"Unexpected error in main: {e}")
    finally:
        log("Shutting down datafeed script...")


if __name__ == "__main__":
    main()