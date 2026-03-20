from engine_datastream import DatastreamEngine
import time

def on_tick(tick):
    print(tick["price"])

def main():
    datastream = DatastreamEngine()
    datastream.start()
    datastream.subscribe(on_tick)

if __name__ == "__main__":
    main()
    time.sleep(100)