SYMBOL = "MESH6"
CONTRACT_ID = 4214195
CONTRACT_LOTS = 4
TIMEFRAME = "5m"
SEQUENCE_LENGTH = 12 # Number of candles to use for prediction
TARGET = 12 # Number of candles to predict forward
HEADSTART = 0 # Number of seconds before candle close to start
RETRAIN_INTERVAL = 5 # Every x minutes, retrain the model
OFFSET = 24 # Number of recent candles to exclude from training
LOOKBACK_WINDOW = 1000 # Number of candles to look back for training
BACKTEST_MODEL_DIR = "./trained_models/backtest"
BACKTEST_STEP = 1  # Step in candles for backtest (1 = every candle)
# Retrain every N candles in backtest. For 5m data, RETRAIN_INTERVAL=5 means every 1 candle in live; use 1 to match loop.
BACKTEST_RETRAIN_EVERY_N_CANDLES = 12