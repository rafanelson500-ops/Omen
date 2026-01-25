import numpy as np
import pandas as pd

def add_value_area_levels(df, lookback=100, price_step=0.25, value_area_pct=0.7):
    """
    Adds VAL and VAH columns to a candle dataframe using rolling volume profile.

    Parameters:
        df (pd.DataFrame): Must contain columns ["open","high","low","close","volume"]
        lookback (int): Number of candles in rolling window
        price_step (float): Price bin size
        value_area_pct (float): % of volume to include in value area (default 70%)

    Returns:
        pd.DataFrame with added columns ["VAL", "VAH"]
    """
    
    df = df.copy()
    df["VAL"] = np.nan
    df["VAH"] = np.nan

    for i in range(lookback, len(df)):
        window = df.iloc[i - lookback:i]

        volume_dict = {}

        # Build volume profile for window
        for _, row in window.iterrows():
            low = row["Low"]
            high = row["High"]
            volume = row["Volume"]

            prices = np.arange(low, high + price_step, price_step)
            if len(prices) == 0:
                continue

            vol_per_level = volume / len(prices)

            for p in prices:
                p_bin = round(p / price_step) * price_step
                volume_dict[p_bin] = volume_dict.get(p_bin, 0) + vol_per_level

        if not volume_dict:
            continue

        vp = pd.Series(volume_dict)

        # Sort by volume descending
        vp_sorted = vp.sort_values(ascending=False)

        total_volume = vp.sum()
        target_volume = total_volume * value_area_pct

        cumulative = 0
        selected_prices = []

        for price, vol in vp_sorted.items():
            cumulative += vol
            selected_prices.append(price)
            if cumulative >= target_volume:
                break

        df.at[df.index[i], "VAL"] = min(selected_prices)
        df.at[df.index[i], "VAH"] = max(selected_prices)

    return df
