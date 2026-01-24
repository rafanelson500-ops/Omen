import torch
import torch.nn as nn
import torch.nn.functional as F

class Predictor(nn.Module):
    """
    Neural network that predicts the next candle percent change
    for multiple assets across multiple timeframes.
    
    Input: (batch, symbols, timeframes, time_steps, features)
    Output: (batch, symbols, timeframes) - predicted percent change
            Formula: (next_close - current_close) / current_close
            Example: 0.02 = 2% increase, -0.01 = 1% decrease
    """

    def __init__(
        self, 
        num_assets, 
        num_timeframes, 
        num_features, 
        time_steps=100,
        lstm_hidden=128,
        lstm_layers=2,
        dropout=0.2
    ):
        super().__init__()  # Calls the init method for the nn.Module class

        # Define model variables
        self.num_assets = num_assets
        self.num_timeframes = num_timeframes
        self.num_features = num_features
        self.time_steps = time_steps
        
        # Feature normalization layer - helps with feature scaling
        self.feature_norm = nn.LayerNorm(num_features)

        # LSTM encoders - one for each timeframe
        self.timeframe_encoders = nn.ModuleList([
            nn.LSTM(
                input_size=num_features,      # 16 features go in
                hidden_size=lstm_hidden,      # 128 hidden units
                num_layers=lstm_layers,       # 2 layers deep
                batch_first=True,             # Batch dimension first
                bidirectional=False,          # Only look forward (past → future)
                dropout=dropout if lstm_layers > 1 else 0
            )
            for _ in range(num_timeframes)  # One for each timeframe
        ])
        
        # After unidirectional LSTM, output size is lstm_hidden (not 2*lstm_hidden)
        lstm_output_dim = lstm_hidden  # 128
        
        # Cross-timeframe attention - finds relationships between timeframes
        self.timeframe_attention = nn.MultiheadAttention(
            embed_dim=lstm_output_dim,
            num_heads=8,              # 8 parallel attention mechanisms
            dropout=dropout,
            batch_first=True
        )
        
        # Cross-asset attention - finds relationships between symbols
        self.asset_attention = nn.MultiheadAttention(
            embed_dim=lstm_output_dim,
            num_heads=8,
            dropout=dropout,
            batch_first=True
        )
        
        # Feed-forward network - processes the features
        self.ffn = nn.Sequential(
            nn.Linear(lstm_output_dim, 128),  # 128 → 128
            nn.GELU(),                         # Activation function
            nn.Dropout(dropout),               # Prevents overfitting
            nn.Linear(128, 128),               # 128 → 128
            nn.GELU(),
            nn.Dropout(dropout),
        )
        
        # Final prediction head - outputs one price per (symbol, timeframe)
        self.prediction_head = nn.Sequential(
            nn.Linear(128, 64),   # 128 → 64
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(64, 1)      # 64 → 1 (one price prediction)
        )

    def forward(self, x):
        """
        Forward pass through the model.
        
        Args:
            x: Input tensor shape (batch, symbols, timeframes, time_steps, features)
        
        Returns:
            predictions: Shape (batch, symbols, timeframes) - predicted percent change
                        (next_close - current_close) / current_close
        """
        batch_size, symbols, timeframes, time_steps, features = x.shape
        
        # Normalize features (helps with scaling issues)
        x = self.feature_norm(x)
        
        # Process each timeframe through its LSTM
        # Reshape: (batch, symbols, timeframes, time_steps, features)
        # For each timeframe, we want: (batch * symbols, time_steps, features)
        encoded_sequences = []
        
        for tf_idx in range(timeframes):
            # Extract data for this specific timeframe
            # x[:, :, tf_idx, :, :] -> (batch, symbols, time_steps, features)
            tf_data = x[:, :, tf_idx, :, :]  # (batch, symbols, time_steps, features)
            
            # Reshape for LSTM: (batch * symbols, time_steps, features)
            tf_data_reshaped = tf_data.view(batch_size * symbols, time_steps, features)
            
            # Pass through LSTM
            lstm_out, (h_n, c_n) = self.timeframe_encoders[tf_idx](tf_data_reshaped)
            
            # Take the last output (most recent information)
            encoded = lstm_out[:, -1, :]  # (batch * symbols, 128)
            encoded_sequences.append(encoded)
        
        # Stack all timeframes: (timeframes, batch * symbols, 128)
        encoded = torch.stack(encoded_sequences, dim=0)
        # Reshape: (batch * symbols, timeframes, 128)
        encoded = encoded.transpose(0, 1)
        
        # Cross-timeframe attention
        encoded, _ = self.timeframe_attention(encoded, encoded, encoded)
        
        # Reshape for cross-asset attention: (batch, symbols, timeframes, 128)
        encoded = encoded.view(batch_size, symbols, timeframes, -1)
        
        # Process each timeframe for cross-asset attention
        timeframe_outputs = []
        for tf_idx in range(timeframes):
            tf_encoded = encoded[:, :, tf_idx, :]  # (batch, symbols, 128)
            
            # Cross-asset attention
            tf_attended, _ = self.asset_attention(tf_encoded, tf_encoded, tf_encoded)
            timeframe_outputs.append(tf_attended)
        
        # Stack: (batch, symbols, timeframes, 128)
        encoded = torch.stack(timeframe_outputs, dim=2)
        
        # Feed-forward network
        encoded = self.ffn(encoded)
        
        # Final prediction
        predictions = self.prediction_head(encoded).squeeze(-1)  # (batch, symbols, timeframes)
        
        return predictions