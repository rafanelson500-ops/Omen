import data_loader
from dataset import ModelDataset
from predictor import Predictor
from train import train_model

SYMBOLS = ["SPY", "QQQ"]
TIMEFRAMES = ["30m", "1h", "1d"]
TIME_STEPS = 100
BATCH_SIZE = 32
LEARNING_RATE = 0.001
NUM_EPOCHS = 50
TRAIN_SPLIT = 0.8  # 80% for training, 20% for validation

def main():
    # Load data
    print("Loading data...")
    X, y = data_loader.get_data(SYMBOLS, TIMEFRAMES, TIME_STEPS)
    print(f"Data loaded: X shape {X.shape}, y shape {y.shape}")
    
    # Create dataset
    print("Creating dataset...")
    model_dataset = ModelDataset(X, y)
    
    # Get model dimensions from data
    num_features = X.shape[4]  # Last dimension is features
    num_symbols = len(SYMBOLS)
    num_timeframes = len(TIMEFRAMES)
    
    # Train model
    train_model(
        dataset=model_dataset,
        num_symbols=num_symbols,
        num_timeframes=num_timeframes,
        num_features=num_features,
        time_steps=TIME_STEPS,
        batch_size=BATCH_SIZE,
        learning_rate=LEARNING_RATE,
        num_epochs=NUM_EPOCHS,
        train_split=TRAIN_SPLIT
    )

if __name__ == "__main__":
    main()