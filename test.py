"""
Test script that samples a random 100-candle window and predicts the next candle.
Shows predicted vs actual IsGreen value.
"""

import numpy as np
import pandas as pd
from data_loader import load_boil_data
from dataset import compute_features
from predictor import load_model, predict_next_candle


def main():
    """
    Test script:
    1. Load BOIL data
    2. Load trained model
    3. Pick a random 100-candle window
    4. Predict the next candle's IsGreen
    5. Show actual vs predicted
    """
    print("=" * 70)
    print("BOIL Candle Prediction Model - Test Script")
    print("=" * 70)
    
    # Load data
    print("\n[Step 1] Loading BOIL historical data (1h candles)...")
    df = load_boil_data(period="60d", interval="1h")
    df_features = compute_features(df)
    print(f"Loaded {len(df_features)} candles")
    
    # Load model
    print("\n[Step 2] Loading trained model...")
    try:
        model = load_model("boil_model.pkl")
        print("Model loaded successfully")
    except FileNotFoundError:
        print("ERROR: Model file 'boil_model.pkl' not found.")
        print("Please run main.py first to train the model.")
        return
    
    # Pick a random 100-candle window
    sequence_length = 10
    # Need at least sequence_length + 1 candles (sequence + next candle)
    # So we can pick from index 0 to len(df) - sequence_length - 1
    max_start_idx = len(df_features) - sequence_length - 1
    
    if max_start_idx < 100:
        print(f"\nNot enough data for a 100-candle window. Using all available data.")
        window_size = max_start_idx + 1
    else:
        window_size = 100
    
    # Random start index for the 100-candle window (truly random each time)
    window_start = np.random.randint(0, max_start_idx - window_size + 1)
    window_end = window_start + window_size
    
    print(f"\n[Step 3] Selected random window: indices {window_start} to {window_end} ({window_size} candles)")
    print(f"Date range: {df_features.index[window_start]} to {df_features.index[window_end-1]}")
    
    # Pick a random sequence within this window
    # The sequence can start anywhere from window_start to window_end - sequence_length
    sequence_start_range = (window_start, window_end - sequence_length)
    sequence_start = np.random.randint(sequence_start_range[0], sequence_start_range[1])
    
    print(f"\n[Step 4] Using sequence starting at index {sequence_start}")
    print(f"Sequence dates: {df_features.index[sequence_start]} to {df_features.index[sequence_start + sequence_length - 1]}")
    
    # Predict next candle
    next_candle_idx = sequence_start + sequence_length
    predicted_class, predicted_prob = predict_next_candle(
        model, df_features, sequence_length=sequence_length, start_idx=sequence_start
    )
    
    # Get actual next candle
    actual_is_green = df_features.iloc[next_candle_idx]['IsGreen']
    actual_close = df_features.iloc[next_candle_idx]['Close']
    actual_open = df_features.iloc[next_candle_idx]['Open']
    actual_pct_change = df_features.iloc[next_candle_idx]['PctChange']
    
    # Display results
    print("\n" + "=" * 70)
    print("PREDICTION RESULTS")
    print("=" * 70)
    print(f"\nNext candle date: {df_features.index[next_candle_idx]}")
    print(f"\nPredicted IsGreen: {predicted_class} ({'Green' if predicted_class == 1 else 'Red'})")
    print(f"Predicted probability (Green): {predicted_prob:.4f}")
    print(f"\nActual IsGreen: {int(actual_is_green)} ({'Green' if actual_is_green == 1 else 'Red'})")
    print(f"Actual Open: ${actual_open:.2f}")
    print(f"Actual Close: ${actual_close:.2f}")
    print(f"Actual PctChange: {actual_pct_change:.2f}%")
    
    # Check if prediction was correct
    is_correct = predicted_class == int(actual_is_green)
    print(f"\n{'✓ CORRECT' if is_correct else '✗ INCORRECT'} prediction")
    print("=" * 70)
    
    # Show some sequence details
    print("\nSequence details (last 3 candles in sequence):")
    print(df_features[['Open', 'High', 'Low', 'Close', 'Volume', 'IsGreen', 'PctChange']].iloc[
        sequence_start + sequence_length - 3:sequence_start + sequence_length
    ])


if __name__ == "__main__":
    main()
