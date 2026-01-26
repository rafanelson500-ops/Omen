from data.data import get_data
from data.features import featurize_HMM, featurize_GBT
from data.cleaner import normalize_HMM_features
from hmm.model import load_model as load_hmm_model, predict_regimes
from gbt.model import load_model as load_gbt_model, predict_with_confidence
import numpy as np
from datetime import datetime, timedelta
import time
from config import SYMBOL, QTY
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce
import os
import dotenv

dotenv.load_dotenv()

API_KEY = os.getenv("API_KEY")
SECRET_KEY = os.getenv("SECRET_KEY")

client = TradingClient(API_KEY, SECRET_KEY, paper=True)

def get_shares_owned():
    try:
        pos = client.get_open_position(SYMBOL)
        return int(pos.qty)
    except Exception as e:
        return 0

def buy():
    shares_owned = get_shares_owned()
    if shares_owned > 0:
        print("Already own shares, can't buy")
        return None
    try:
        market_order_data = MarketOrderRequest(
            symbol=SYMBOL,
            qty=QTY,
            side=OrderSide.BUY,
            time_in_force=TimeInForce.GTC
        )
        order = client.submit_order(market_order_data)
        print("Successfully bought {QTY} shares of {SYMBOL}")
    except Exception as e:
        return None

def sell():
    shares_owned = get_shares_owned()
    if shares_owned == 0:
        print("No shares owned, can't sell")
        return None
    try:
        market_order_data = MarketOrderRequest(
            symbol=SYMBOL,
            qty=QTY,
            side=OrderSide.SELL,
            time_in_force=TimeInForce.GTC
        )
        order = client.submit_order(market_order_data)
        print("Successfully sold {QTY} shares of {SYMBOL}")
    except Exception as e:
        print("Can't short, alredy closed")
        return None

def get_sleep_time():
    # gets amount of time until nmext minute
    now = datetime.now()
    next_minute = now.replace(second=0, microsecond=0) + timedelta(minutes=1)
    return (next_minute - now).total_seconds()

def main():
    # Get data
    while True:
        data = get_data(training=False)
        
        # Add features for HMM (to define regions)
        data = featurize_HMM(data)
        data = featurize_GBT(data)
        
        # Drop NaN values from rolling calculations
        data.dropna(inplace=True)
        
        # Normalize HMM features
        data = normalize_HMM_features(data)
        
        # Extract normalized features for HMM prediction
        features_normalized = data[['Returns', 'RealizedVolatility', 'Autocorrelation']].values
        
        # Load trained HMM model and predict regimes
        hmm_model = load_hmm_model("./trained_models/hmm_model.pkl")
        regimes = predict_regimes(hmm_model, features_normalized)
        data['Regieme'] = regimes
        
        # Load trained GBT model and generate predictions with confidence
        gbt_model, sequence_length = load_gbt_model("./trained_models/gbt_model.pkl")
        
        # Set minimum return threshold to cover transaction costs (0.1% for 1-minute trading)
        min_return_threshold = 0.001  # 0.1%
        data = predict_with_confidence(gbt_model, data, sequence_length, min_return_threshold=min_return_threshold)

        # Strategy: use predicted returns to generate trading signals
        # Signal = 1 for buy (predicted return > threshold), -1 for sell (predicted return < -threshold), 0 for hold
        leverage = 1
        # Use predicted return magnitude scaled by confidence for position sizing
        data["Strategy"] = np.where(
            data['Signal'] == 1, 
            1,  # Buy: positive position
            np.where(
                data['Signal'] == -1,
                data['PredictedReturn'] * data['Confidence'] * leverage,  # Sell: negative position
                0  # Hold: no position
            )
        )
        
        # Get the Strategy value for the next candle (last row)
        next_strategy = data['Strategy'].iloc[-1]
        
        # Determine action based on Strategy value
        if next_strategy > 0:
            action = "BUY"
            buy()
        elif next_strategy < 0:
            action = "SELL"
            sell()
        else:
            action = "HOLD"
        
        print(action)
    
        time.sleep(get_sleep_time())

if __name__ == "__main__":
    data = main()
