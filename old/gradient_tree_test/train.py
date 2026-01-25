"""
Training workflow for the Gradient Boosted Trees model.
Handles data splitting, training, evaluation, and model persistence.
"""

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, confusion_matrix, classification_report
import joblib
import os
from dataset import compute_features, create_sequences, flatten_sequences


def train_model(df: pd.DataFrame, sequence_length: int = 10, test_size: float = 0.2, 
                val_size: float = 0.1, random_state: int = 42, 
                model_save_path: str = "boil_model.pkl") -> GradientBoostingClassifier:
    """
    Train a Gradient Boosted Trees model on candle sequences.
    
    Args:
        df: DataFrame with OHLCV data
        sequence_length: Number of candles in each sequence
        test_size: Proportion of data for test set
        val_size: Proportion of remaining data for validation set
        random_state: Random seed for reproducibility
        model_save_path: Path to save the trained model
    
    Returns:
        Trained GradientBoostingClassifier model
    """
    # Compute features
    print("Computing features...")
    df_features = compute_features(df)
    
    # Create sequences
    print(f"Creating sequences with length {sequence_length}...")
    X, y = create_sequences(df_features, sequence_length=sequence_length)
    
    print(f"Created {len(X)} sequences")
    print(f"Feature distribution - IsGreen=1: {np.sum(y)}, IsGreen=0: {len(y) - np.sum(y)}")
    
    # Flatten sequences for gradient boosted trees
    X_flat = flatten_sequences(X)
    
    # Split data: train -> val/test split -> val/test
    print("Splitting data...")
    X_train, X_temp, y_train, y_temp = train_test_split(
        X_flat, y, test_size=(test_size + val_size), random_state=random_state, stratify=y
    )
    
    # Split temp into validation and test
    val_ratio = val_size / (test_size + val_size)
    X_val, X_test, y_val, y_test = train_test_split(
        X_temp, y_temp, test_size=(1 - val_ratio), random_state=random_state, stratify=y_temp
    )
    
    print(f"Train set: {len(X_train)} samples")
    print(f"Validation set: {len(X_val)} samples")
    print(f"Test set: {len(X_test)} samples")
    
    # Train model
    print("Training Gradient Boosted Trees model...")
    model = GradientBoostingClassifier(
        n_estimators=100,
        learning_rate=0.1,
        max_depth=5,
        random_state=random_state,
        verbose=1
    )
    
    model.fit(X_train, y_train)
    
    # Evaluate on validation set
    print("\nValidation set evaluation:")
    y_val_pred = model.predict(X_val)
    val_accuracy = accuracy_score(y_val, y_val_pred)
    print(f"Validation Accuracy: {val_accuracy:.4f}")
    print("\nValidation Confusion Matrix:")
    print(confusion_matrix(y_val, y_val_pred))
    
    # Evaluate on test set
    print("\nTest set evaluation:")
    y_test_pred = model.predict(X_test)
    test_accuracy = accuracy_score(y_test, y_test_pred)
    print(f"Test Accuracy: {test_accuracy:.4f}")
    print("\nTest Confusion Matrix:")
    print(confusion_matrix(y_test, y_test_pred))
    print("\nTest Classification Report:")
    print(classification_report(y_test, y_test_pred))
    
    # Save model
    print(f"\nSaving model to {model_save_path}...")
    joblib.dump(model, model_save_path)
    print("Model saved successfully!")
    
    return model
