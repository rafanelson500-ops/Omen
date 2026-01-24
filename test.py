import torch
import matplotlib.pyplot as plt
import numpy as np
from predictor import Predictor
from main import SYMBOLS, TIMEFRAMES, TIME_STEPS
from data_loader import get_data

# Model parameters (must match training)
num_features = 16
num_symbols = len(SYMBOLS)
num_timeframes = len(TIMEFRAMES)

# Create model (same architecture as training)
model = Predictor(
    num_assets=num_symbols,
    num_timeframes=num_timeframes,
    num_features=num_features,
    time_steps=TIME_STEPS
)

# Load trained weights
try:
    checkpoint = torch.load('unnormalized.pth', map_location='cpu')
    model.load_state_dict(checkpoint['model_state_dict'])
    model.eval()
    print("Model loaded successfully!")
    print(f"Model was trained for {checkpoint.get('epoch', 'unknown')} epochs")
    print(f"Best validation loss: {checkpoint.get('val_loss', 'unknown'):.6f}")
except Exception as e:
    print(f"Error loading model: {e}")
    print("Using untrained model (random weights) for testing...")
    model.eval()

# Quick test: Check if model can produce different outputs with different inputs
print("\nTesting model architecture with random inputs...")
test_input1 = torch.randn(1, num_symbols, num_timeframes, TIME_STEPS, num_features)
test_input2 = torch.randn(1, num_symbols, num_timeframes, TIME_STEPS, num_features)
with torch.no_grad():
    test_pred1 = model(test_input1)
    test_pred2 = model(test_input2)
print(f"  Random input 1 predictions:\n    {test_pred1[0]}")
print(f"  Random input 2 predictions:\n    {test_pred2[0]}")
pred_diff = torch.abs(test_pred1 - test_pred2).mean().item()
print(f"  Prediction difference: {pred_diff:.6f}")
if pred_diff < 1e-5:
    print("  ⚠️  WARNING: Model outputs are nearly identical! Architecture may have an issue.")
else:
    print("  ✅ Model can produce different outputs - architecture looks OK")

# Load all data
print("Loading data...")
X, y = get_data(SYMBOLS, TIMEFRAMES, TIME_STEPS)
print(f"Data shape: X {X.shape}, y {y.shape}")

# Get predictions for all samples
print("Making predictions...")
X_tensor = torch.FloatTensor(X)

# Debug: Check if inputs are varying
print(f"\nInput data stats:")
print(f"  X min: {X.min():.6f}, max: {X.max():.6f}, mean: {X.mean():.6f}, std: {X.std():.6f}")
print(f"  X first sample range: {X[0].min():.6f} to {X[0].max():.6f}")
print(f"  X last sample range: {X[-1].min():.6f} to {X[-1].max():.6f}")
print(f"  Are first and last samples different? {not np.allclose(X[0], X[-1])}")

with torch.no_grad():
    predictions = model(X_tensor)  # Shape: (samples, symbols, timeframes)

# Convert to numpy
predictions = predictions.numpy()  # Shape: (samples, symbols, timeframes)
y_actual = y  # Shape: (samples, symbols, timeframes)

# Debug: Check prediction variance
print(f"\nPrediction stats:")
print(f"  Predictions shape: {predictions.shape}")
print(f"  Predictions min: {predictions.min():.6f}, max: {predictions.max():.6f}")
print(f"  Predictions mean: {predictions.mean():.6f}, std: {predictions.std():.6f}")
print(f"  SPY predictions - min: {predictions[:, 0, 0].min():.6f}, max: {predictions[:, 0, 0].max():.6f}, std: {predictions[:, 0, 0].std():.6f}")
print(f"  QQQ predictions - min: {predictions[:, 1, 0].min():.6f}, max: {predictions[:, 1, 0].max():.6f}, std: {predictions[:, 1, 0].std():.6f}")
print(f"  First 5 SPY predictions: {predictions[:5, 0, 0]}")
print(f"  First 5 QQQ predictions: {predictions[:5, 1, 0]}")

# Use first timeframe (30m) for plotting, or average across timeframes
# Using first timeframe for simplicity
timeframe_idx = 0
timeframe_name = TIMEFRAMES[timeframe_idx]

# Extract predictions and actuals for each symbol
# Shape: (samples,)
spy_predicted = predictions[:, 0, timeframe_idx]  # SPY, first timeframe
spy_actual = y_actual[:, 0, timeframe_idx]
qqq_predicted = predictions[:, 1, timeframe_idx]  # QQQ, first timeframe
qqq_actual = y_actual[:, 1, timeframe_idx]

# Create time axis (sample indices)
num_samples = len(spy_predicted)
time_axis = np.arange(num_samples)

# Create the plot
plt.figure(figsize=(14, 8))

# Plot SPY
plt.plot(time_axis, spy_predicted * 100, label='SPY Predicted', 
         color='blue', linestyle='--', linewidth=1.5, alpha=0.7)
plt.plot(time_axis, spy_actual * 100, label='SPY Actual', 
         color='blue', linestyle='-', linewidth=1.5)

# Plot QQQ
plt.plot(time_axis, qqq_predicted * 100, label='QQQ Predicted', 
         color='red', linestyle='--', linewidth=1.5, alpha=0.7)
plt.plot(time_axis, qqq_actual * 100, label='QQQ Actual', 
         color='red', linestyle='-', linewidth=1.5)

# Add labels and title
plt.xlabel('Sample Index', fontsize=12)
plt.ylabel('Percent Change (%)', fontsize=12)
plt.title(f'Predicted vs Actual Returns - {timeframe_name} Timeframe', fontsize=14, fontweight='bold')
plt.legend(loc='best', fontsize=10)
plt.grid(True, alpha=0.3)

# Add horizontal line at 0%
plt.axhline(y=0, color='black', linestyle='-', linewidth=0.5, alpha=0.3)

# Add some statistics
spy_mae = np.mean(np.abs(spy_predicted - spy_actual)) * 100
qqq_mae = np.mean(np.abs(qqq_predicted - qqq_actual)) * 100

# Add text box with statistics
stats_text = f'Mean Absolute Error:\nSPY: {spy_mae:.4f}%\nQQQ: {qqq_mae:.4f}%'
plt.text(0.02, 0.98, stats_text, transform=plt.gca().transAxes,
         fontsize=9, verticalalignment='top',
         bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))

plt.tight_layout()
plt.savefig('predictions_vs_actual.png', dpi=300, bbox_inches='tight')
print(f"\nGraph saved as 'predictions_vs_actual.png'")
print(f"SPY MAE: {spy_mae:.4f}%")
print(f"QQQ MAE: {qqq_mae:.4f}%")

plt.show()