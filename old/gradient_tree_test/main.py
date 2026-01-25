"""
Main script to orchestrate the training pipeline.
Follows the steps outlined in docs.md.
"""

from data_loader import load_boil_data
from train import train_model


def main():
    """
    Main training pipeline:
    1. Load BOIL historical data
    2. Compute features
    3. Create sequences
    4. Train model
    5. Evaluate and save model
    """
    print("=" * 70)
    print("BOIL Candle Prediction Model - Training Pipeline")
    print("=" * 70)
    
    # Step 1: Load data
    print("\n[Step 1] Loading BOIL historical data (1h candles)...")
    df = load_boil_data(period="60d", interval="1h")
    print(f"Loaded {len(df)} candles")
    print(f"Date range: {df.index[0]} to {df.index[-1]}")
    
    # Steps 2-7: Train model (this handles feature computation, sequence creation, 
    # splitting, training, evaluation, and saving)
    print("\n[Steps 2-7] Training model...")
    model = train_model(
        df=df,
        sequence_length=10,
        test_size=0.2,
        val_size=0.1,
        random_state=42,
        model_save_path="boil_model.pkl"
    )
    
    print("\n" + "=" * 70)
    print("Training pipeline completed successfully!")
    print("=" * 70)


if __name__ == "__main__":
    main()
