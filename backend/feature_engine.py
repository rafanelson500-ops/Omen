import pandas as pd
import numpy as np

class FeatureEngine:
    def __init__(self):
        pass
    
    def add_heikin_ashi(self, df):
        """
        Calculate Heikin-Ashi candles using proper formulas:
        - HA Close = (Open + High + Low + Close) / 4
        - HA Open = (Previous HA Open + Previous HA Close) / 2
        - HA High = max(High, HA Open, HA Close)
        - HA Low = min(Low, HA Open, HA Close)
        """
        # Initialize arrays
        ha_open = np.zeros(len(df))
        ha_high = np.zeros(len(df))
        ha_low = np.zeros(len(df))
        ha_close = np.zeros(len(df))
        
        # First candle: HA Open = (Open + Close) / 2
        ha_open[0] = (df['open'].iloc[0] + df['close'].iloc[0]) / 2
        ha_close[0] = (df['open'].iloc[0] + df['high'].iloc[0] + df['low'].iloc[0] + df['close'].iloc[0]) / 4
        ha_high[0] = max(df['high'].iloc[0], ha_open[0], ha_close[0])
        ha_low[0] = min(df['low'].iloc[0], ha_open[0], ha_close[0])
        
        # Subsequent candles
        for i in range(1, len(df)):
            ha_close[i] = (df['open'].iloc[i] + df['high'].iloc[i] + df['low'].iloc[i] + df['close'].iloc[i]) / 4
            ha_open[i] = (ha_open[i-1] + ha_close[i-1]) / 2
            ha_high[i] = max(df['high'].iloc[i], ha_open[i], ha_close[i])
            ha_low[i] = min(df['low'].iloc[i], ha_open[i], ha_close[i])
        
        df['ha_open'] = ha_open
        df['ha_high'] = ha_high
        df['ha_low'] = ha_low
        df['ha_close'] = ha_close
        return df

    def featurize_candles(self, candles):
        df = pd.DataFrame(candles)
        df = self.add_heikin_ashi(df)
        return df.fillna(0)