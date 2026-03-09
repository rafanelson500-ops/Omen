import helpers.data as data
import helpers.features as features
import helpers.processor as processor
import helpers.monte_carlo as monte_carlo
import joblib
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import hmmlearn.hmm as hmm
import numpy as np
import flask
from flask import jsonify, request
from flask_cors import CORS

app = flask.Flask(__name__)
CORS(app)

hmm_features = ["efficiency_ratio_6", "efficiency_ratio_12", "efficiency_ratio_24", "rv_short_med_ratio", "mean_deviation", "vol_expansion", "hurst"]
gbt_features = ["hmm_state", "ema_dist", "ema_dist_abs", "ema_div_chg_3", "ema_div_chg_6", "ret_ema_align", "ema_slope", "ema_slope_chg", "ema_dist_zscore", "vol_ratio_fast", "vol_ratio_slow", "vwap_dist", "range_pos"]
sequence_length = 16
train_size = 0.6  # Match training split
validation_size = 0.2

mode = "validation"

def create_sequences(data, features, exclude_last_n=0):
    """Create sequences for GBT prediction matching training format.
    
    Args:
        data: DataFrame with features
        features: List of feature column names
        exclude_last_n: Number of last candles to exclude (for live predictions)
    """
    feature_data = data[features].values
    X_sequences = []
    valid_indices = []
    
    # Only use completed candles (exclude the last N candles for live predictions)
    max_idx = len(data) - exclude_last_n
    
    # Create sliding windows
    for i in range(sequence_length, max_idx):
        # Get sequence of previous candles (not including current candle)
        # This uses candles i-12 to i-1, which is correct for live predictions
        sequence = feature_data[i - sequence_length:i]
        
        # Skip if any NaN in the sequence (needed for valid prediction)
        if np.isnan(sequence).any():
            continue
            
        # Flatten the sequence into a single feature vector
        flattened_sequence = sequence.flatten()
        X_sequences.append(flattened_sequence)
        valid_indices.append(i)
    
    return np.array(X_sequences), valid_indices

def graph_notation(df):
    df["graph:0:red"] = df["ema"]

    df["graph:1:grey"] = df["target"]
    df["graph:1:red"] = df["gbt_target"]

    df["graph:3:yellow"] = df["signal"]

    df["graph:2:grey"] = df["base_cumulative"]
    df["graph:2:green"] = df["strategy_cumulative"]
    return df

@app.route("/data")
def get_data():
    df = data.get_data().iloc[-int(len(data.get_data()) * (1-train_size)):]
    df = features.add_features(df)
    if mode == "validation":
        df = df.iloc[int(len(df) * train_size):int(len(df) * (train_size + validation_size))]
    else:
        df = df.iloc[int(len(df) * (train_size + validation_size)):]
    # Only drop rows where essential features are missing (not target)
    df = df.dropna(subset=[col for col in df.columns if col != 'target'])
    
    hmm = joblib.load("trained_models/regime_hmm.pkl")
    df["hmm_state"] = hmm.predict(df[hmm_features])
    df = features.add_target(df)
    df["target"] = df["target"].fillna(0)

    X_sequences, valid_indices = create_sequences(df, gbt_features, exclude_last_n=0)
    gbt = joblib.load("trained_models/gbt.pkl")
    predictions = gbt.predict(X_sequences)  # continuous [-1, 1]
    df["gbt_target"] = np.nan
    df.loc[df.index[valid_indices], "gbt_target"] = predictions
    
    df = processor.process_data(df)

    df = graph_notation(df)
    
    return jsonify(df.dropna().to_dict(orient="records"))

@app.route("/monte-carlo", methods=["POST"])
def run_monte_carlo_simulation():
    """Run Monte Carlo simulation and return results."""
    try:
        data_request = request.get_json()
        num_simulations = int(data_request.get("num_simulations", 1000))
        
        if num_simulations < 1 or num_simulations > 10000:
            return jsonify({"error": "num_simulations must be between 1 and 10000"}), 400
        
        # Load and prepare data (same as /data endpoint)
        df = data.get_data().iloc[-int(len(data.get_data()) * (1-train_size)):]
        df = features.add_features(df)
        if mode == "validation":
            df = df.iloc[int(len(df) * train_size):int(len(df) * (train_size + validation_size))]
        else:
            df = df.iloc[int(len(df) * (train_size + validation_size)):]
        df = df.dropna(subset=[col for col in df.columns if col != 'target'])
        
        hmm_model = joblib.load("trained_models/regime_hmm.pkl")
        df["hmm_state"] = hmm_model.predict(df[hmm_features])
        
        df = features.add_target(df)
        df["target"] = df["target"].fillna(0)
        
        # Create sequences and get predictions
        X_sequences, valid_indices = create_sequences(df, gbt_features, exclude_last_n=0)
        gbt = joblib.load("trained_models/gbt.pkl")
        predictions = gbt.predict(X_sequences)  # continuous [-1, 1]
        
        df["gbt_target"] = np.nan
        df.loc[df.index[valid_indices], "gbt_target"] = predictions
        
        # Process data to get base_returns
        df = processor.process_data(df)
        
        # Run Monte Carlo simulation
        results = monte_carlo.run_monte_carlo(df, num_simulations)
        
        return jsonify(results)
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=8000)