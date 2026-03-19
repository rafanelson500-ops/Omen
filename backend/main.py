from datafeed import Datafeed
import time

def main():
    datafeed = Datafeed()
    datafeed.start()

if __name__ == "__main__":
    main()
    time.sleep(100)