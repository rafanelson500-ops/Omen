"""
Main project pipeline.
This is going to be a state-based strategy to trade the NYSE open on CME.
There will be states that describe current strategy conditions on a larger timeframe.
Executions will occur on the 1s timeframe.

States Example:

"""
import time
from database.datafeed import start as start_datafeed


# Fires everytime a 1s candle is completed.
def handle_candle(candle):
    print(candle)

# Initialize the pipeline
def main():
    start_datafeed(handle_candle)

if __name__ == "__main__":
    print("Starting pipeline")
    main()
    try:
        print("Running pipeline")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Keyboard interrupt")
    finally:
        print("Pipeline stopped")