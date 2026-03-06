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

hmm_features = ["mean_spread", "spread_std", "vol_accel", "har_rv", "mean_compression", "composite_mean"]
gbt_features = ["hmm_state", "mean_divergence", "divergence_change", "mean_velocity", "dist_vah", "dist_val", "composite_mean", "har_rv", "har_sigma", "vol_accel"]
sequence_length = 12
train_size = 0.6  # Match training split

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
    # composite mean
    df["graph:0:white"] = df["composite_mean"]
    # sigma lines
    df["graph:0:yellow:sig1upper"] = df["composite_mean"] + df["har_sigma"]
    df["graph:0:yellow:sig1lower"] = df["composite_mean"] - df["har_sigma"]
    df["graph:0:orange:sig1.5upper"] = df["composite_mean"] + df["har_sigma"] * 1.5
    df["graph:0:orange:sig1.5lower"] = df["composite_mean"] - df["har_sigma"] * 1.5
    df["graph:0:red:sig2upper"] = df["composite_mean"] + df["har_sigma"] * 2
    df["graph:0:red:sig2lower"] = df["composite_mean"] - df["har_sigma"] * 2

    # target
    #df["graph:1:green"] = df["target"]
    # Fill NaN gbt_target with 0 for rows where we couldn't predict (not enough history)
    df["graph:1:red"] = df["gbt_target"].fillna(0)

    # Strategy
    df["graph:2:grey"] = df["base_cumulative"]
    df["graph:2:green"] = df["strategy_cumulative"]
    
    return df

@app.route("/data")
def get_data():
    df = data.get_data().iloc[-int(len(data.get_data()) * (1-train_size)):]
    df = features.add_features(df)
    # Only drop rows where essential features are missing (not target)
    df = df.dropna(subset=[col for col in df.columns if col != 'target'])
    
    hmm = joblib.load("trained_models/regime_hmm.pkl")
    df["hmm_state"] = hmm.predict(df[hmm_features])
    
    # Add target column - set to 0 where it can't be calculated (last 3 candles due to shift(-3))
    df = features.add_target(df)
    df["target"] = df["target"].fillna(0)  # Set NaN target values to 0 for current/recent candles
    
    # For live predictions: use gbt_features (no target to avoid data leakage)
    # The model should be retrained with gbt_features - see train.ipynb
    # Sequences use candles i-12 to i-1 (12 previous completed candles, not including i)
    # This ensures we only use historical data available at prediction time
    # Predict up to and including the current candle
    X_sequences, valid_indices = create_sequences(df, gbt_features, exclude_last_n=0)
    
    # Make predictions for all valid sequences (including current candle)
    # Each prediction uses only historical data (12 previous completed candles)
    gbt = joblib.load("trained_models/gbt.pkl")
    # Use predict_proba to get probabilities (0-1) instead of binary predictions (0 or 1)
    predictions = gbt.predict_proba(X_sequences)[:, 1]  # Probability of class 1
    
    # Initialize gbt_target column with NaN
    df["gbt_target"] = np.nan
    # Fill predictions only for valid indices (where we have complete sequences)
    # Predictions are for candle i, using only historical data from i-12 to i-1
    # This is suitable for live predictions: no lookahead bias
    df.loc[df.index[valid_indices], "gbt_target"] = predictions
    
    # Don't drop rows - keep all data up to current candle
    # Only fill NaN in gbt_target for rows where we couldn't predict (not enough history)
    # But keep those rows in the output
    
    df = processor.process_data(df)
    df = graph_notation(df)
    
    # Return all data up to the current candle (last 480 rows for performance)
    # This includes the current candle with predictions
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
        df = df.dropna(subset=[col for col in df.columns if col != 'target'])
        
        hmm_model = joblib.load("trained_models/regime_hmm.pkl")
        df["hmm_state"] = hmm_model.predict(df[hmm_features])
        
        df = features.add_target(df)
        df["target"] = df["target"].fillna(0)
        
        # Create sequences and get predictions
        X_sequences, valid_indices = create_sequences(df, gbt_features, exclude_last_n=0)
        gbt = joblib.load("trained_models/gbt.pkl")
        predictions = gbt.predict_proba(X_sequences)[:, 1]
        
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