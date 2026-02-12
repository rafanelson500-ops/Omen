from datetime import datetime, timedelta
import time
import os
from data.data import get_data
from config.config import (
    HEADSTART, LOOKBACK_WINDOW, SEQUENCE_LENGTH, OFFSET, TARGET, RETRAIN_INTERVAL,
    BACKTEST_MODEL_DIR, BACKTEST_STEP, BACKTEST_RETRAIN_EVERY_N_CANDLES,
)

# Number of most recent bars to always keep for signalling (avoid delayed signal from dropna)
SIGNAL_TAIL_BARS = max(1, TARGET)
from data.features import add_features
import matplotlib.pyplot as plt
import joblib
from hmm.model import train_hmm, predict_regimes, features as HMM_FEATURES
from gbt.model import train_gbt, predict_with_quartiles
import plotly.graph_objects as go
import numpy as np
import pandas as pd
from broker import buy, sell, refresh_tokens

def get_sleep_time(current_time):
    next_time = current_time.replace(second=0, microsecond=0) + timedelta(minutes=5-current_time.minute%5)
    return max(0, (next_time - current_time).total_seconds() - HEADSTART)

def load_hmm(df, model_dir=None):
    base = model_dir if model_dir is not None else "./trained_models"
    path = os.path.join(base, "regieme_model.pkl")
    os.makedirs(base, exist_ok=True)
    try:
        model = joblib.load(path)
    except Exception:
        print("No regieme model found, training new model...")
        model = train_hmm(df.iloc[:-OFFSET] if len(df) > OFFSET else df, model_dir=base)
    return model

def load_gbt(df, model_dir=None):
    base = model_dir if model_dir is not None else "./trained_models"
    path = os.path.join(base, "gbt_model.pkl")
    os.makedirs(base, exist_ok=True)
    try:
        model = joblib.load(path)
    except Exception:
        print("No gbt model found, training new model...")
        try:
            model = train_gbt(df.iloc[:-OFFSET], model_dir=base)
        except ValueError as e:
            print(f"Error training GBT model: {e}")
            print("Attempting to use existing model or creating minimal model...")
            try:
                model = joblib.load(path)
                print("Using existing model despite training error")
            except Exception:
                raise ValueError(f"Could not train or load GBT model: {e}") from e
    return model

def get_signal(df_slice, model_dir, hmm_model=None, gbt_model=None):
    """
    Get signal for the last candle in df_slice (no file I/O).
    Returns (signal, close_price, timestamp).
    """
    feature_cols = [col for col in df_slice.columns if col not in ['ForwardReturn', 'IsGreen']]
    work = df_slice.dropna(subset=feature_cols).iloc[-LOOKBACK_WINDOW:].copy()
    if len(work) == 0:
        return 0, float('nan'), df_slice.index[-1] if len(df_slice) else None
    if hmm_model is None:
        hmm_model = load_hmm(work, model_dir=model_dir)
    work['Regieme'] = predict_regimes(hmm_model, work)
    if gbt_model is None:
        gbt_model = load_gbt(work, model_dir=model_dir)
    work = predict_with_quartiles(gbt_model, work)
    work['PredictedPrice'] = work['Close'] * (1 + work['PredictedReturn'].fillna(0))
    crossed_above = (work['PredictedPrice'] > work['Close']) & (work['PredictedPrice'].shift(1) <= work['Close'].shift(1))
    crossed_below = (work['PredictedPrice'] < work['Close']) & (work['PredictedPrice'].shift(1) >= work['Close'].shift(1))
    work['Signal'] = np.where(crossed_above, 1, np.where(crossed_below, -1, 0))
    non_zero = work.loc[work['Signal'] != 0, 'Signal']
    signal = int(non_zero.iloc[-1]) if len(non_zero) > 0 else 0
    price = work['Close'].iloc[-1]
    ts = work.index[-1]
    return signal, price, ts

def process_data(df):
    print("Adding features to data...")
    # Only drop NaN rows for feature columns (not ForwardReturn, which is only for training).
    # Always keep the last SIGNAL_TAIL_BARS so we signal on the latest timestamp, not delayed data.
    feature_cols = [col for col in df.columns if col not in ['ForwardReturn', 'IsGreen']]
    subset = [c for c in feature_cols if c in df.columns]
    if not subset:
        df = df.iloc[0:0]
    else:
        # Drop NaN only among rows that are NOT in the last SIGNAL_TAIL_BARS (keep latest bars for signalling)
        n = len(df)
        tail_size = min(SIGNAL_TAIL_BARS, n)
        if tail_size < n:
            df_body = df.iloc[: n - tail_size].dropna(subset=subset)
            df_tail = df.iloc[-tail_size:]
            df = pd.concat([df_body, df_tail], axis=0)
        # Forward-fill feature NaNs in the tail so HMM/GBT get valid inputs for the latest bar(s)
        tail_idx = df.index[-tail_size:]
        df.loc[tail_idx, subset] = df[subset].ffill().loc[tail_idx]
    df = df.iloc[-LOOKBACK_WINDOW:]

    # Add regiemes to data
    hmm_model = load_hmm(df)
    df['Regieme'] = predict_regimes(hmm_model, df)

    # Add Predictions
    gbt_model = load_gbt(df)
    df = predict_with_quartiles(gbt_model, df)
    df.dropna(inplace=False)

    df['PredictedPrice'] = df['close'] * (1 + df['PredictedReturn'].fillna(0))

    crossed_above = (df['PredictedPrice'] > df['close']) & (df['PredictedPrice'].shift(1) <= df['close'].shift(1))
    crossed_below = (df['PredictedPrice'] < df['close']) & (df['PredictedPrice'].shift(1) >= df['close'].shift(1))
    df['Signal'] = np.where(crossed_above, 1, np.where(crossed_below, -1, 0))
    
    print(df[['close','PredictedPrice', 'Signal']].tail(24))

    signal = 0
    non_zero = df.loc[df['Signal'] != 0, 'Signal']
    signal = int(non_zero.iloc[-1]) if len(non_zero) > 0 else 0

    current_price = df['close'].iloc[-1]
    last_ts = df.index[-1][-1] if isinstance(df.index[-1], tuple) else df.index[-1]

    if signal == 1:
        buy()
        with open('signal.txt', 'a') as f:
            f.write(last_ts.strftime('%Y-%m-%d %H:%M:%S') + '\t' + '+1' + '\t' + str(current_price) + '\n')
    elif signal == -1:
        sell()
        with open('signal.txt', 'a') as f:
            f.write(last_ts.strftime('%Y-%m-%d %H:%M:%S') + '\t' + '-1' + '\t' + str(current_price) + '\n')

def loop():
    while True:
        # Get & print current time
        current_time = datetime.now()
        print(f"Current time: {current_time}")

        # Get data
        df = get_data()

        # Add features to data
        df = add_features(df)
        process_data(df)
        # Retrain model if needed
        if current_time.minute % RETRAIN_INTERVAL == 0:
            refresh_tokens()
            print("Retraining model")
            os.makedirs("./trained_models", exist_ok=True)
            # HMM needs rows with no NaN in its features
            train_df = df.dropna(subset=HMM_FEATURES)
            train_df = train_df.iloc[:-OFFSET] if len(train_df) > OFFSET else train_df
            hmm_model = None
            if len(train_df) > 50:
                try:
                    hmm_model = train_hmm(train_df)
                except Exception as e:
                    print(f"Error retraining HMM model: {e}")
                    print("Continuing with existing HMM model...")
                    try:
                        hmm_model = load_hmm(df)
                    except Exception:
                        hmm_model = None
            if hmm_model is not None:
                df_regime = df.dropna(subset=HMM_FEATURES).copy()
                df_regime["Regieme"] = predict_regimes(hmm_model, df_regime)
                df_regime = df_regime.iloc[:-OFFSET] if len(df_regime) > OFFSET else df_regime
                if len(df_regime) > 20:
                    try:
                        train_gbt(df_regime)
                    except ValueError as e:
                        print(f"Error retraining GBT model: {e}")
                        print("Continuing with existing GBT model...")
                    except Exception as e:
                        print(f"Unexpected error retraining GBT model: {e}")
                        print("Continuing with existing GBT model...")

        # Sleep for remaining time
        sleep_time = get_sleep_time(datetime.now())
        print(f"Sleeping for {sleep_time} seconds")
        time.sleep(sleep_time)

if __name__ == "__main__":
    loop()