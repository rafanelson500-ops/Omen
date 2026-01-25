"""
Visualization for SPY close price with regime indicators.
Uses matplotlib to create plots showing market regimes.
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from typing import Optional


def plot_spy_with_regimes(df: pd.DataFrame, regimes: np.ndarray, save_path: Optional[str] = None) -> None:
    """
    Create matplotlib visualization showing SPY close price with regime indicators.
    
    Args:
        df: DataFrame with Close prices (indexed by date)
        regimes: Array of regime labels (0, 1, 2) aligned with df
        save_path: Optional path to save the plot (default: "spy_regime_detection.png")
    """
    # Align regimes with dataframe
    # Ensure regimes array matches dataframe length
    if len(regimes) != len(df):
        raise ValueError(f"Regimes array length ({len(regimes)}) must match dataframe length ({len(df)})")
    regime_series = pd.Series(regimes, index=df.index)
    
    # Create figure with two subplots
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10), sharex=True, 
                                    gridspec_kw={'height_ratios': [3, 1], 'hspace': 0.1})
    
    # Regime colors
    regime_colors = {
        0: 'green',      # Low volatility regime
        1: 'yellow',     # Medium volatility regime
        2: 'red'         # High volatility regime
    }
    
    regime_names = {
        0: 'Regime 0 (Low Vol)',
        1: 'Regime 1 (Medium Vol)',
        2: 'Regime 2 (High Vol)'
    }
    
    # Convert index to numeric for shading (matplotlib needs numeric x values for axvspan)
    dates = df.index
    if isinstance(dates, pd.DatetimeIndex):
        dates_numeric = mdates.date2num(dates)
    else:
        dates_numeric = np.arange(len(dates))
    
    # Add colored background regions for regimes on price plot
    current_regime = regime_series.iloc[0]
    start_idx = 0
    
    for i in range(1, len(regime_series)):
        if regime_series.iloc[i] != current_regime or i == len(regime_series) - 1:
            end_idx = i if i < len(regime_series) - 1 else len(regime_series)
            
            # Add vertical span for this regime period
            if isinstance(df.index, pd.DatetimeIndex):
                ax1.axvspan(dates[start_idx], dates[end_idx - 1], 
                           alpha=0.3, color=regime_colors[current_regime], 
                           label=regime_names[current_regime] if start_idx == 0 or current_regime != regime_series.iloc[start_idx - 1] else "")
            else:
                ax1.axvspan(start_idx, end_idx - 1, 
                           alpha=0.3, color=regime_colors[current_regime],
                           label=regime_names[current_regime] if start_idx == 0 or current_regime != regime_series.iloc[start_idx - 1] else "")
            
            start_idx = i
            current_regime = regime_series.iloc[i]
    
    # Plot 1: SPY Close Price
    ax1.plot(df.index, df['Close'], 'k-', linewidth=2, label='SPY Close')
    ax1.set_ylabel('Price ($)', fontsize=12)
    ax1.set_title('SPY Close Price with Market Regime Detection', fontsize=14, fontweight='bold')
    ax1.grid(True, alpha=0.3)
    ax1.legend(loc='upper left', fontsize=9)
    
    # Plot 2: Regime indicator
    ax2.fill_between(df.index, 0, regime_series.values, alpha=0.6, 
                     color=[regime_colors[r] for r in regime_series.values], step='pre')
    ax2.plot(df.index, regime_series.values, 'k-', linewidth=1.5, alpha=0.7)
    ax2.set_ylabel('Regime', fontsize=12)
    ax2.set_xlabel('Date', fontsize=12)
    ax2.set_ylim(-0.2, 2.2)
    ax2.set_yticks([0, 1, 2])
    ax2.set_yticklabels(['0', '1', '2'])
    ax2.grid(True, alpha=0.3, axis='y')
    
    # Format x-axis dates
    if isinstance(df.index, pd.DatetimeIndex):
        ax2.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
        ax2.xaxis.set_major_locator(mdates.MonthLocator(interval=6))
        plt.setp(ax2.xaxis.get_majorticklabels(), rotation=45, ha='right')
    
    plt.tight_layout()
    
    # Save the plot
    output_path = save_path if save_path else "spy_regime_detection.png"
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    print(f"Plot saved to {output_path}")
    
    # Show the plot
    plt.show()
