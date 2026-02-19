import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from datetime import datetime, timezone

file_path = "./logs.txt"

def log(message):
    with open(file_path, "a") as f:
        f.write(datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S") + " - " + message + "\n")

def get_logs():
    with open(file_path, "r") as f:
        return f.read()