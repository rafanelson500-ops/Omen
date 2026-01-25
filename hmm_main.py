"""
Main script to orchestrate the HMM regime detection pipeline.
Loads SPY data, calculates features, trains HMM, and visualizes results.
"""

import pandas as pd
import numpy as np
from spy_data_loader import load_spy_data
from feature_calculator import prepare_features
from hmm_model import train_hmm, predict_regimes, save_model
from visualizer import plot_spy_with_regimes


def main():
    """
    Main pipeline:
    1. Load SPY data (5 years for training, max for visualization)
    2. Calculate features (returns, realized_vol, autocorrelation)
    3. Train HMM with 3 regimes
    4. Predict regimes on full dataset
    5. Visualize results
    6. Save model
    """
    print("=" * 70)
    print("SPY Hidden Markov Model - Regime Detection")
    print("=" * 70)
    
    # Step 1: Load SPY data for training (5 years)
    print("\n[Step 1] Loading SPY historical data (5 years for training)...")
    df_train = load_spy_data(period="5y", interval="1d")
    print(f"Loaded {len(df_train)} trading days")
    print(f"Date range: {df_train.index[0]} to {df_train.index[-1]}")
    
    # Step 2: Calculate features for training
    print("\n[Step 2] Calculating features (returns, realized_vol, autocorrelation)...")
    features_df_train, features_array_train = prepare_features(df_train)
    print(f"Features calculated: {len(features_array_train)} samples")
    print(f"Feature statistics:")
    print(f"  Returns: mean={features_df_train['returns'].mean():.6f}, std={features_df_train['returns'].std():.6f}")
    print(f"  Realized Vol: mean={features_df_train['realized_vol'].mean():.6f}, std={features_df_train['realized_vol'].std():.6f}")
    print(f"  Autocorrelation: mean={features_df_train['autocorrelation'].mean():.6f}, std={features_df_train['autocorrelation'].std():.6f}")
    
    # Step 3: Train HMM model
    print("\n[Step 3] Training HMM model with 3 regimes...")
    hmm_model = train_hmm(features_array_train, n_components=3, n_iter=100, random_state=42)
    print("HMM model trained successfully")
    print(f"Model converged: {hmm_model.monitor_.converged}")
    print(f"Iterations: {hmm_model.monitor_.iter}")
    
    # Step 4: Load full dataset for visualization (max period)
    print("\n[Step 4] Loading full SPY dataset (max period) for visualization...")
    df_full = load_spy_data(period="max", interval="1d")
    print(f"Loaded {len(df_full)} trading days")
    print(f"Date range: {df_full.index[0]} to {df_full.index[-1]}")
    
    # Calculate features for full dataset
    print("\n[Step 5] Calculating features for full dataset...")
    features_df_full, features_array_full = prepare_features(df_full)
    print(f"Features calculated: {len(features_array_full)} samples")
    
    # Predict regimes on full dataset
    print("\n[Step 6] Predicting regimes on full dataset...")
    regimes_full = predict_regimes(hmm_model, features_array_full)
    
    # Count regimes
    unique, counts = np.unique(regimes_full, return_counts=True)
    print("\nRegime distribution:")
    for regime, count in zip(unique, counts):
        percentage = (count / len(regimes_full)) * 100
        print(f"  Regime {regime}: {count} days ({percentage:.2f}%)")
    
    # Step 7: Visualize results
    print("\n[Step 7] Creating visualization...")
    # Align df_full with features (drop rows that were removed during feature calculation)
    df_aligned = df_full.loc[features_df_full.index]
    plot_spy_with_regimes(df_aligned, regimes_full, save_path="spy_regime_detection.png")
    
    # Step 8: Save model
    print("\n[Step 8] Saving model...")
    save_model(hmm_model, "spy_hmm_model.pkl")
    
    print("\n" + "=" * 70)
    print("Pipeline completed successfully!")
    print("=" * 70)
    print("\nFiles created:")
    print("  - spy_hmm_model.pkl (trained HMM model)")
    print("  - spy_regime_detection.png (visualization)")


if __name__ == "__main__":
    main()
