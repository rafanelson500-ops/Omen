from config.config import TRADE_SYMBOL, QTY
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
        pos = client.get_open_position(TRADE_SYMBOL)
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
            symbol=TRADE_SYMBOL,
            qty=QTY,
            side=OrderSide.BUY,
            time_in_force=TimeInForce.GTC
        )
        order = client.submit_order(market_order_data)
        print(f"Successfully bought {QTY} shares of {TRADE_SYMBOL}")
    except Exception as e:
        return None

def sell():
    shares_owned = get_shares_owned()
    if shares_owned == 0:
        print("No shares owned, can't sell")
        return None
    try:
        market_order_data = MarketOrderRequest(
            symbol=TRADE_SYMBOL,
            qty=QTY,
            side=OrderSide.SELL,
            time_in_force=TimeInForce.GTC
        )
        order = client.submit_order(market_order_data)
        print(f"Successfully sold {QTY} shares of {TRADE_SYMBOL}")
    except Exception as e:
        print("Can't short, alredy closed")
        return None