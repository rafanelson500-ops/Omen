import numpy as np
import pandas as pd
import datetime

class Backtester:
    def __init__(self):
        pass

    def interpret_candles(self, df):
        """
        NYSE Open Strategy:
        - Enter on strong momentum with volume confirmation
        - Use order flow (delta) to confirm direction
        - Exit on absorption signals or when momentum fades
        """
        # Base signal: Heikin-Ashi trend
        ha_bullish = df["ha_close"] > df["ha_open"]
        
        # Momentum filter: relaxed threshold (40th percentile instead of 60th)
        has_momentum = df["momentum_strength"] > df["momentum_strength"].rolling(20).quantile(0.4)
        
        # Volume confirmation: relaxed (1.1x instead of 1.5x)
        volume_ok = df["vol_surge"] > 1.1
        
        # Order flow confirmation: delta momentum in same direction
        bullish_flow = df["delta_momentum"] > 0
        bearish_flow = df["delta_momentum"] < 0
        
        # Flow imbalance: relaxed threshold (50th percentile instead of 70th)
        decent_flow = np.abs(df["flow_imbalance"]) > df["flow_imbalance"].abs().rolling(20).quantile(0.5)
        
        # Avoid extreme absorption zones only (relaxed to 85th percentile)
        extreme_absorption = df["absorption"] > df["absorption"].rolling(30).quantile(0.85)
        
        # Long conditions: bullish HA + (momentum OR volume) + bullish flow + decent flow
        long_signal = (
            ha_bullish & 
            (has_momentum | volume_ok) &  # Either momentum OR volume (OR instead of AND)
            bullish_flow & 
            decent_flow &
            ~extreme_absorption
        )
        
        # Short conditions: bearish HA + (momentum OR volume) + bearish flow + decent flow
        short_signal = (
            ~ha_bullish & 
            (has_momentum | volume_ok) &  # Either momentum OR volume
            bearish_flow & 
            decent_flow &
            ~extreme_absorption
        )
        
        # Exit conditions: strong reversal signals
        long_exit = (
            ~ha_bullish & 
            bearish_flow & 
            (extreme_absorption | (df["momentum_strength"] < df["momentum_strength"].rolling(20).quantile(0.2)))
        )
        
        short_exit = (
            ha_bullish & 
            bullish_flow & 
            (extreme_absorption | (df["momentum_strength"] < df["momentum_strength"].rolling(20).quantile(0.2)))
        )
        
        # Initialize position tracking
        df["position"] = 0
        df["entry_time"] = np.nan
        min_hold_seconds = 5  # Minimum hold time in seconds
        
        current_position = 0
        entry_second = None
        
        for i in range(len(df)):
            # Check if we should exit current position
            if current_position != 0:
                seconds_held = df["second"].iloc[i] - entry_second if entry_second is not None else 0
                
                # Exit if minimum hold time passed AND exit signal triggered
                if seconds_held >= min_hold_seconds:
                    if (current_position > 0 and long_exit.iloc[i]) or (current_position < 0 and short_exit.iloc[i]):
                        current_position = 0
                        entry_second = None
                # Or exit if we've held for a while (max hold ~30 seconds)
                elif seconds_held >= 30:
                    current_position = 0
                    entry_second = None
            
            # Enter new position if no current position
            if current_position == 0:
                if long_signal.iloc[i]:
                    current_position = 1
                    entry_second = df["second"].iloc[i]
                elif short_signal.iloc[i]:
                    current_position = -1
                    entry_second = df["second"].iloc[i]
            
            df.loc[df.index[i], "position"] = current_position
        
        return df

    def compute_returns(self, df):
        df["strategy_returns"] = np.cumsum(df["position"].shift(1) * df["return"])
        df["benchmark_returns"] = np.cumsum(df["return"])
        return df

    def backtest(self, df):
        df = self.interpret_candles(df)
        df = self.compute_returns(df)
        return df.fillna(0)