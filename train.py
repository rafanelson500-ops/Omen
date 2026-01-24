import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader, random_split
import numpy as np
from predictor import Predictor
from dataset import ModelDataset

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

def train_model(
    dataset: ModelDataset,
    num_symbols: int,
    num_timeframes: int,
    num_features: int,
    time_steps: int,
    batch_size: int = 32,
    learning_rate: float = 0.001,
    num_epochs: int = 50,
    train_split: float = 0.8
):
    """
    Main training function.
    Trains the model and saves the best model.
    
    Args:
        dataset: The ModelDataset containing X and y
        num_symbols: Number of symbols (assets)
        num_timeframes: Number of timeframes
        num_features: Number of features per candle
        time_steps: Number of historical candles
        batch_size: Batch size for training
        learning_rate: Learning rate for optimizer
        num_epochs: Number of training epochs
        train_split: Fraction of data to use for training (rest for validation)
    """
    print(f"Using device: {DEVICE}")
    print("=" * 60)
    
    # Step 1: Split into train and validation sets
    train_size = int(train_split * len(dataset))
    val_size = len(dataset) - train_size
    train_dataset, val_dataset = random_split(dataset, [train_size, val_size])
    
    print(f"Train samples: {train_size}, Validation samples: {val_size}")
    
    # Step 2: Create data loaders (handles batching)
    train_loader = DataLoader(
        train_dataset, 
        batch_size=batch_size, 
        shuffle=True,  # Shuffle training data
        num_workers=0  # Set to 0 for Windows compatibility
    )
    val_loader = DataLoader(
        val_dataset, 
        batch_size=batch_size, 
        shuffle=False,  # Don't shuffle validation
        num_workers=0
    )
    
    # Step 3: Create model
    print("Creating model...")
    model = Predictor(
        num_assets=num_symbols,
        num_timeframes=num_timeframes,
        num_features=num_features,
        time_steps=time_steps
    ).to(DEVICE)
    
    # Count parameters
    total_params = sum(p.numel() for p in model.parameters())
    trainable_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
    print(f"Model created with {total_params:,} total parameters ({trainable_params:,} trainable)")
    
    # Step 4: Define loss function and optimizer
    criterion = nn.MSELoss()  # Mean Squared Error - measures how wrong predictions are
    optimizer = optim.AdamW(
        model.parameters(), 
        lr=learning_rate,
        weight_decay=1e-5  # Small regularization
    )
    
    # Learning rate scheduler - reduces learning rate if validation loss stops improving
    scheduler = optim.lr_scheduler.ReduceLROnPlateau(
        optimizer, 
        mode='min',  # Minimize validation loss
        factor=0.5,  # Reduce LR by half
        patience=5  # Wait 5 epochs before reducing
    )
    
    # Step 5: Training loop
    print("\n" + "=" * 60)
    print("Starting training...")
    print("=" * 60)
    
    best_val_loss = float('inf')
    train_losses = []
    val_losses = []
    
    for epoch in range(num_epochs):
        # Training phase
        model.train()  # Set model to training mode
        train_loss = 0.0
        train_batches = 0
        
        for batch_idx, (batch_X, batch_y) in enumerate(train_loader):
            # Move data to device (GPU if available)
            batch_X = batch_X.to(DEVICE)
            batch_y = batch_y.to(DEVICE)
            
            # Zero gradients (clear previous gradients)
            optimizer.zero_grad()
            
            # Forward pass - get predictions
            predictions = model(batch_X)
            
            # Calculate loss
            loss = criterion(predictions, batch_y)
            
            # Backward pass - calculate gradients
            loss.backward()
            
            # Clip gradients to prevent exploding gradients
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
            
            # Update weights
            optimizer.step()
            
            train_loss += loss.item()
            train_batches += 1
        
        # Average training loss
        avg_train_loss = train_loss / train_batches
        
        # Validation phase
        model.eval()  # Set model to evaluation mode
        val_loss = 0.0
        val_batches = 0
        
        with torch.no_grad():  # Don't calculate gradients for validation (faster)
            for batch_X, batch_y in val_loader:
                batch_X = batch_X.to(DEVICE)
                batch_y = batch_y.to(DEVICE)
                
                predictions = model(batch_X)
                loss = criterion(predictions, batch_y)
                
                val_loss += loss.item()
                val_batches += 1
        
        # Average validation loss
        avg_val_loss = val_loss / val_batches
        
        # Update learning rate based on validation loss
        scheduler.step(avg_val_loss)
        
        # Store losses for plotting later
        train_losses.append(avg_train_loss)
        val_losses.append(avg_val_loss)
        
        # Print progress
        current_lr = optimizer.param_groups[0]['lr']
        print(f"Epoch {epoch+1}/{num_epochs} | "
              f"Train Loss: {avg_train_loss:.6f} | "
              f"Val Loss: {avg_val_loss:.6f} | "
              f"LR: {current_lr:.6f}")
        
        # Save best model
        if avg_val_loss < best_val_loss:
            best_val_loss = avg_val_loss
            torch.save({
                'epoch': epoch + 1,
                'model_state_dict': model.state_dict(),
                'optimizer_state_dict': optimizer.state_dict(),
                'val_loss': avg_val_loss,
                'train_losses': train_losses,
                'val_losses': val_losses,
            }, 'best_model.pth')
            print(f"  → Saved best model (val loss: {avg_val_loss:.6f})")
    
    print("\n" + "=" * 60)
    print("Training complete!")
    print(f"Best validation loss: {best_val_loss:.6f}")
    print(f"Model saved to: best_model.pth")
    print("=" * 60)
    
    return model, train_losses, val_losses


if __name__ == "__main__":
    # This won't work without data - use main.py instead
    print("Please run main.py to train the model")
