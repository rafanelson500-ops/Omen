MODE = "paper"
SYMBOL = "MESH6"
CONTRACT_ID = 4214195
CONTRACT_LOTS = 1

WINDOW_START = "10:00"
WINDOW_END = "15:00"
WINDOW_CROSSES_DAY = False

TIMEFRAME = "5m"
SEQUENCE_LENGTH = 12 # Number of candles to use for prediction
TARGET = 12 # Number of candles to predict forward
HEADSTART = 0 # Number of seconds before candle close to start
RETRAIN_INTERVAL = 5 # Every x minutes, retrain the model
OFFSET = 24 # Number of recent candles to exclude from training
LOOKBACK_WINDOW = 1000 # Number of candles to look back for training