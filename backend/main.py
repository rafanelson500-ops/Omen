"""
Main project pipeline.
This is going to be a state-based strategy to trade the NYSE open on CME.
There will be states that describe current strategy conditions on a larger timeframe.
Executions will occur on the 1s timeframe.

Definitions:
- TPO Bias:                        1s - The direction of the TPO bias in relation to the current price.
- Tapped LVN:                      1s - The price of an LVN which price has touched
- Tapped LVN Direction:            1s - The direction of which the price came from to touch the LVN 
- Tapped Single Print:             1s - The price of the single print of which the price has visted
- Tapped Single Print Direction:   1s - The direction of which the price came from to touch the single print
- Absorption_Occured:              1m - High order delta in one direction, but contrary no movement
    * I = (buy - sell) / (buy + sell)
    * A = I / (𝚫price + 0.01)

Entry Criteria:
- TPO Bias allignment
- LVN Reversal
- Absorption Occured
- Opposite Delta Spike

"""
import time
from typing import Literal, TypedDict
from database.datafeed import start as start_datafeed
from flask import Flask, request, jsonify
from flask_socketio import SocketIO

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

class States(TypedDict):
    tpo_bias: Literal["bullish", "bearish", "neutral"]
    tapped_lvn: float
    tapped_lvn_direction: Literal[-1,0,1]
    tapped_single_print: float
    tapped_single_print_direction: Literal[-1,0,1]
    absorption: float


states: States = {
    "tpo_bias": "neutral", # The direction of the TPO bias in relation to the current price.
    "tapped_lvn": 0.0,
    "absorption": 0.0,
}

# Fires everytime a 1s candle is completed.
def handle_new_candle(candle):
    socketio.emit("candle", candle)

def handle_update_candle(candle):
    socketio.emit("update_candle", candle)
    
# Initialize the pipeline
def main():
    start_datafeed(handle_new_candle, handle_update_candle)

if __name__ == "__main__":
    print("Starting pipeline")
    main()
    socketio.run(app, host="0.0.0.0", port=8000)