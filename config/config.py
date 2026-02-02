SYMBOL = "ES=F"
TRADE_SYMBOL = "SPY"
TIMEFRAME = "5m"
SEQUENCE_LENGTH = 12 # Number of candles to use for prediction
TARGET = 12 # Number of candles to predict forward
HEADSTART = 1 # Number of seconds before candle close to start
QTY = 10 # Maximum number of shares to buy or sell
RETRAIN_INTERVAL = 15 # Every x minutes, retrain the model
OFFSET = 100 # Number of recent candles to exclude from training
LOOKBACK_WINDOW = 1000 # Number of candles to look back for training