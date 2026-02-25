import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from datetime import datetime, timezone
from helpers.timing import get_sleep_time
from helpers.config_handler import load_config
import time
from helpers.data_handler import get_data
from helpers.features import add_regime_features, add_technical_features, add_prediction_features_chop, add_prediction_features_trend, add_targets
from helpers.hmm import load_model as load_hmm, predict_regimes, train_hmm
from helpers.gbt.chop_gbt import load_model as load_chop_model, predict_chop_target, train_chop_gbt
from helpers.gbt.trend_gbt import load_model as load_trend_model, predict_trend_target, train_trend_gbt
from helpers.broker import buy, sell, close_all
import pandas as pd
from helpers.logs import log
import numpy as np

training = False

def train_models():
    global training
    if not training:
        config = load_config()
        training = True
        # Get all available data, then use 1/5 for training
        all_data = get_data(data = config["session"], jsonify = False, include_volume = True, all_data = True)
        # Take first 1/5 of data for training (maintains chronological order)
        data = all_data.iloc[0:len(all_data) // 5]
        data = add_regime_features(data)
        data = add_technical_features(data)
        data = add_prediction_features_chop(data)
        data = add_prediction_features_trend(data)
        data = add_targets(data)
        cols_to_check = [c for c in data.columns if c not in ["forward_return", "target"]]
        data.dropna(subset=cols_to_check, inplace=True)
        train_hmm(data, model_dir = "backtest_models")
        hmm_model = load_hmm("backtest_models/regime_model.pkl", data)
        data["regime"] = predict_regimes(hmm_model, data)
        train_chop_gbt(data, model_dir = "backtest_models")
        train_trend_gbt(data, model_dir = "backtest_models")
        training = False
        return data

def backtest():
    config = load_config()

    data = get_data(config["session"], jsonify = False, include_volume = True, all_data = True)
    print(data.head())

    # Featurize data
    data = add_regime_features(data)
    data = add_technical_features(data)
    data = add_prediction_features_chop(data)
    data = add_prediction_features_trend(data)
    data = add_targets(data)
    
    # Drop all rows with NaN except in 'forward_return' and 'target'
    cols_to_check = [c for c in data.columns if c not in ["forward_return", "target"]]
    data = data.dropna(subset=cols_to_check).iloc[len(data)//5:]


    # Run HMM model to get probabilities of each regime
    hmm_model = load_hmm("backtest_models/regime_model.pkl", data.iloc[:1500])
    data["regime"] = predict_regimes(hmm_model, data)

    # Run Chop & Trend GBTs
    # Note: predict functions will automatically exclude signal columns to match training data
    chop_model = load_chop_model("backtest_models/chop_gbt_model.pkl", data.iloc[:1500])
    data = predict_chop_target(chop_model, data)

    trend_model = load_trend_model("backtest_models/trend_gbt_model.pkl", data.iloc[:1500])
    data = predict_trend_target(trend_model, data)

    # Weight & average predictions according to regime probabilities
    data['weighted_signal'] = data['regime'] * data['chop_signal'] + (1 - data['regime']) * data['trend_signal']
    data['position'] = np.where(data['weighted_signal'] > config["confidence_threshold"], 1, np.where(data['weighted_signal'] < -config["confidence_threshold"], -1, 0))
    data['position'] = np.where(data['position'] == 0, data['position'].shift(1), data['position'])
    
    # Calculate returns
    cols_to_check = [c for c in data.columns if c not in ["forward_return", "target"]]
    data.dropna(subset=cols_to_check, inplace=True)
    
    # Calculate raw P&L (price difference) from one candle to the next
    # This represents the actual dollar change in price
    data['price_change'] = data['close'] - data['close'].shift(1)
    # Handle first row (no previous close) and session gaps
    data['price_change'] = data['price_change'].fillna(0)
    # Set price change to 0 for new sessions (gaps > 5 minutes)
    data['price_change'] = np.where(data['new_session'] == 1, 0, data['price_change'])
    
    # Simulated stop loss: for each contiguous position signal, track cumulative
    # PnL from entry. If it drops to or below -stop_loss_threshold, zero out the
    # remaining candles of that signal.
    stop_loss_threshold = 10
    positions = data['position'].values.copy()
    price_changes = data['price_change'].values
    i = 0
    n = len(positions)
    while i < n:
        if positions[i] == 0:
            i += 1
            continue
        # Start of a new signal (entry)
        entry_pos = positions[i]
        cum_pnl = 0.0
        entry_idx = i
        i += 1  # move to next candle; PnL accrues from candle after entry
        while i < n and positions[i] == entry_pos:
            # PnL at this candle = price_change * direction of the signal
            cum_pnl += price_changes[i] * entry_pos
            if cum_pnl <= -stop_loss_threshold:
                # Stop loss hit — zero out from this candle onward in the signal
                while i < n and positions[i] == entry_pos:
                    positions[i] = 0
                    i += 1
                break
            i += 1
    data['position'] = positions
    
    # Buy-and-hold strategy: hold 1 unit, P&L is the raw price change
    # At each candle, we earn/lose the price change
    data['buy_hold_pnl'] = data['price_change']
    
    # Strategy P&L: multiply price change by position from previous candle
    # At candle i, we use position[i-1] (decided at previous candle) to determine our exposure
    # If position[i-1] = 1: we're long, earn full price_change
    # If position[i-1] = -1: we're short, earn -price_change (inverse)
    # If position[i-1] = 0: we're flat, earn 0
    data['strategy_pnl'] = data['price_change'] * data['position'].shift(1).fillna(0)
    
    # Calculate cumulative sum of P&L (starting from 0)
    # This gives us the cumulative profit/loss in dollar terms
    data['cum_strategy'] = data['strategy_pnl'].cumsum()
    data['cum_buy_hold'] = data['buy_hold_pnl'].cumsum()
    
    #Return 2nd half of data
    return data

def monte_carlo_backtest():
    config = load_config()
    data = get_data(config["session"], jsonify = False, include_volume = True, all_data = True)
    data = add_regime_features(data)
    data = add_technical_features(data)
    data = add_prediction_features_chop(data)
    data = add_prediction_features_trend(data)
    data = add_targets(data)

    results = {
        "iterations": [],
        "average_return"
    }
    return data

if __name__ == "__main__":
    train_models()