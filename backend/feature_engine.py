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

    def add_volume_features(self, df):
        """Volume and order flow features for NYSE open"""
        total_vol = df['buy_vol'] + df['sell_vol']
        
        # Volume surge: current volume vs rolling average
        df['vol_ma_20'] = total_vol.rolling(window=20, min_periods=1).mean()
        df['vol_surge'] = total_vol / (df['vol_ma_20'] + 1e-9)
        
        # Delta momentum: rate of change in delta
        df['delta_change'] = df['delta'].diff()
        df['delta_momentum'] = df['delta_change'].rolling(window=5, min_periods=1).sum()
        
        # Order flow imbalance: delta / total volume
        df['flow_imbalance'] = df['delta'] / (total_vol + 1e-9)
        
        # Volume-weighted price position: where is price relative to range
        df['price_position'] = (df['close'] - df['low']) / (df['high'] - df['low'] + 1e-9)
        
        return df
    
    def add_poc_features(self, df):
        """Point of Control (POC) from price_levels"""
        def get_poc(price_levels):
            if not price_levels or not isinstance(price_levels, dict):
                return None, 0
            max_vol = 0
            poc_price = None
            for price, (buy, sell) in price_levels.items():
                level_vol = buy + sell
                if level_vol > max_vol:
                    max_vol = level_vol
                    poc_price = price
            return poc_price, max_vol
        
        poc_data = df['price_levels'].apply(get_poc)
        df['poc_price'] = poc_data.apply(lambda x: x[0] if x[0] is not None else df['close'].iloc[0])
        df['poc_volume'] = poc_data.apply(lambda x: x[1])
        
        # Distance from POC
        df['poc_distance'] = (df['close'] - df['poc_price']) / (df['close'] + 1e-9)
        
        return df
    
    def add_momentum_features(self, df):
        """Price momentum and acceleration features"""
        # Price velocity: rate of change
        df['price_velocity'] = df['close'].pct_change()
        
        # Price acceleration: change in velocity
        df['price_acceleration'] = df['price_velocity'].diff()
        
        # Range expansion: current range vs average range
        df['range'] = df['high'] - df['low']
        df['range_ma_10'] = df['range'].rolling(window=10, min_periods=1).mean()
        df['range_expansion'] = df['range'] / (df['range_ma_10'] + 1e-9)
        
        # Momentum strength: price change relative to range
        df['momentum_strength'] = abs(df['close'] - df['open']) / (df['range'] + 1e-9)
        
        return df
    
    def add_absorption_features(self, df, window=30):
        """Absorption/rejection signals using rolling percentiles"""
        total_vol = df['buy_vol'] + df['sell_vol']
        epsilon = 1e-9
        
        # Aggression: how one-sided is the flow
        df['aggression'] = np.abs(df['delta']) / (total_vol + epsilon)
        
        # Price efficiency: how much did price move vs range
        df['price_efficiency'] = np.abs(df['close'] - df['open']) / (df['high'] - df['low'] + epsilon)
        
        # Volume concentration at POC
        df['vol_concentration'] = df['poc_volume'] / (total_vol + epsilon)
        
        # Rolling percentile ranks
        def rolling_pct_rank(series, window):
            def rank_last(x):
                if len(x) == 0:
                    return 0.5
                return pd.Series(x).rank(pct=True).iloc[-1]
            return series.rolling(window=window, min_periods=1).apply(rank_last, raw=False)
        
        df['aggression_rank'] = rolling_pct_rank(df['aggression'], window)
        df['efficiency_rank'] = rolling_pct_rank(df['price_efficiency'], window)
        df['concentration_rank'] = rolling_pct_rank(df['vol_concentration'], window)
        
        # Absorption score: high aggression + low efficiency + high concentration = absorption
        df['absorption'] = df['aggression_rank'] - df['efficiency_rank'] + df['concentration_rank']
        
        return df

    def featurize_candles(self, candles):
        df = pd.DataFrame(candles)
        df = self.add_heikin_ashi(df)
        df["return"] = df["close"] - df["close"].shift(1)
        df = self.add_volume_features(df)
        df = self.add_poc_features(df)
        df = self.add_momentum_features(df)
        df = self.add_absorption_features(df)
        return df.fillna(0)