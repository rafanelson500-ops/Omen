from datetime import datetime, timedelta
import time
import os
from data.data import get_data
from config.config import (
    HEADSTART, LOOKBACK_WINDOW, SEQUENCE_LENGTH, OFFSET, TARGET, RETRAIN_INTERVAL,
    BACKTEST_MODEL_DIR, BACKTEST_STEP, BACKTEST_RETRAIN_EVERY_N_CANDLES,
)
from data.features import add_features
import matplotlib.pyplot as plt
import joblib
from hmm.model import train_hmm, predict_regimes, features as HMM_FEATURES
from gbt.model import train_gbt, predict_with_quartiles
import plotly.graph_objects as go
import numpy as np

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
    # Only drop NaN rows for feature columns (not ForwardReturn, which is only for training)
    # This allows us to keep the last TARGET candles for prediction even though ForwardReturn is NaN
    feature_cols = [col for col in df.columns if col not in ['ForwardReturn', 'IsGreen']]
    df = df.dropna(subset=feature_cols)
    df = df.iloc[-LOOKBACK_WINDOW:]

    # Add regiemes to data
    hmm_model = load_hmm(df)
    df['Regieme'] = predict_regimes(hmm_model, df)

    # Add Predictions
    gbt_model = load_gbt(df)
    df = predict_with_quartiles(gbt_model, df)
    df.dropna(inplace=False)

    df['PredictedPrice'] = df['Close'] * (1 + df['PredictedReturn'].fillna(0))

    crossed_above = (df['PredictedPrice'] > df['Close']) & (df['PredictedPrice'].shift(1) <= df['Close'].shift(1))
    crossed_below = (df['PredictedPrice'] < df['Close']) & (df['PredictedPrice'].shift(1) >= df['Close'].shift(1))
    df['Signal'] = np.where(crossed_above, 1, np.where(crossed_below, -1, 0))
    
    print(df[['Close','PredictedPrice', 'Signal']].tail(24))

    signal = 0
    non_zero = df.loc[df['Signal'] != 0, 'Signal']
    signal = int(non_zero.iloc[-1]) if len(non_zero) > 0 else 0

    current_price = df['Close'].iloc[-1]

    if signal == 1:
        with open('signal.txt', 'a') as f:
            f.write(df.index[-1].strftime('%Y-%m-%d %H:%M:%S') + '\t' + '+1' + '\t' + str(current_price) + '\n')
    elif signal == -1:
        with open('signal.txt', 'a') as f:
            f.write(df.index[-1].strftime('%Y-%m-%d %H:%M:%S') + '\t' + '-1' + '\t' + str(current_price) + '\n')

def loop():
    last_candle = None
    while True:
        # Get & print current time
        current_time = datetime.now()
        print(f"Current time: {current_time}")

        # Get data
        df = get_data()
        if df.index[-1] == last_candle:
            time.sleep(HEADSTART)
            sleep_time = get_sleep_time(datetime.now())
            print(f"Sleeping for {sleep_time} seconds")
            time.sleep(sleep_time)
            continue
        last_candle = df.index[-1]

        # Add features to data
        df = add_features(df)
        process_data(df)

        # Retrain model if needed
        if current_time.minute % RETRAIN_INTERVAL == 0:
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

def backtest():
    import pandas as pd
    df = get_data()
    df = add_features(df)
    feature_cols = [col for col in df.columns if col not in ['ForwardReturn', 'IsGreen']]
    df = df.dropna(subset=feature_cols)
    num_candles = df.shape[0]
    os.makedirs(BACKTEST_MODEL_DIR, exist_ok=True)
    # Overwrite signal.txt: one line per candle
    signal_file = open("signal.txt", "w")
    rows = []
    hmm_model, gbt_model = None, None
    t = LOOKBACK_WINDOW
    while t < num_candles:
        # Retrain every N candles to match live (no look-ahead)
        if (t - LOOKBACK_WINDOW) % BACKTEST_RETRAIN_EVERY_N_CANDLES == 0:
            train_df = df.iloc[:t].copy()
            if len(train_df) > SEQUENCE_LENGTH + 10:
                try:
                    hmm_model = train_hmm(
                        train_df.iloc[:-OFFSET] if len(train_df) > OFFSET else train_df,
                        model_dir=BACKTEST_MODEL_DIR,
                    )
                    train_df["Regieme"] = predict_regimes(hmm_model, train_df)
                    if "Regieme" in train_df.columns and len(train_df) > OFFSET:
                        gbt_model = train_gbt(train_df.iloc[:-OFFSET], model_dir=BACKTEST_MODEL_DIR)
                except Exception as e:
                    print(f"Backtest retrain at t={t}: {e}")
        df_slice = df.iloc[t - LOOKBACK_WINDOW : t].copy()
        signal, price, ts = get_signal(df_slice, BACKTEST_MODEL_DIR, hmm_model=hmm_model, gbt_model=gbt_model)
        line = f"{ts}\t{signal}\t{price}\n"
        signal_file.write(line)
        signal_file.flush()  # so you can see data as it processes (e.g. tail -f signal.txt)
        # Signal is for the last candle in slice (index t-1); store t-1 so PnL uses return (t-1)->t
        rows.append((ts, signal, price, t - 1))
        t += BACKTEST_STEP
    signal_file.close()
    # PnL and metrics
    if len(rows) < 2:
        print("Backtest: not enough candles for PnL")
        return
    bt_df = pd.DataFrame(rows, columns=["timestamp", "signal", "price", "idx"])
    bt_df = bt_df.set_index("timestamp")
    # Align with df for next-period returns
    closes = df["Close"].values
    idxs = bt_df["idx"].astype(int).values
    returns = []
    for i, idx in enumerate(idxs):
        if idx + 1 < len(closes):
            ret = (closes[idx + 1] / closes[idx]) - 1.0
            returns.append(bt_df["signal"].iloc[i] * ret)
        else:
            returns.append(0.0)
    bt_df["strategy_return"] = returns
    total_return = (1 + pd.Series(returns)).prod() - 1
    n_trades = (bt_df["signal"].diff().fillna(0).abs() > 0).sum()
    equity = (1 + pd.Series(returns)).cumprod()
    peak = equity.cummax()
    drawdown = (equity - peak) / peak
    max_dd = drawdown.min()
    bars = len(returns)
    if bars >= 2:
        sharpe = np.sqrt(252 * 24 * 12) * pd.Series(returns).mean() / (pd.Series(returns).std() or 1e-8)
    else:
        sharpe = 0.0
    print("--- Backtest results ---")
    print(f"Total return:     {total_return:.4f} ({100*total_return:.2f}%)")
    print(f"Sharpe (approx):  {sharpe:.2f}")
    print(f"Num trades:       {n_trades}")
    print(f"Max drawdown:     {max_dd:.4f} ({100*max_dd:.2f}%)")
    print(f"Candles:          {bars}")


if __name__ == "__main__":
    loop()