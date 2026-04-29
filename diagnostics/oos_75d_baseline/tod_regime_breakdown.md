# OOS Time-of-Day + Side×Regime Breakdown

Total OOS trades: 158

## Time of day

bucket,n,win_rate,expectancy,total_pnl,per_trade_sharpe,is_n,is_sharpe,is_pnl
opening_drive,37,0.4595,66.96,2477.5,0.0878,39,0.091,3068.0
morning_2,1,0.0,-1430.0,-1430.0,,1,,-205.0
lunch,0,,,0.0,,0,,0.0
afternoon_1,20,0.45,68.44,1368.75,0.1345,22,0.521,5615.0
afternoon_2,93,0.4946,5.95,553.75,0.0136,107,0.232,14640.0
closing_drive,7,0.7143,169.11,1183.75,0.3367,5,0.63,1531.0


## Side × Regime

bucket,n,win_rate,expectancy,total_pnl,per_trade_sharpe
LONG side × long-gamma,33,0.5758,74.55,2460.0,0.1968
LONG side × short-gamma,29,0.5862,128.41,3723.75,0.2052
SHORT side × long-gamma,48,0.3958,-86.77,-4165.0,-0.1507
SHORT side × short-gamma,48,0.4583,44.48,2135.0,0.0782
LONG side (all regimes),62,0.5806,99.74,6183.75,0.1972
SHORT side (all regimes),96,0.4271,-21.15,-2030.0,-0.0369
BOTH sides × long-gamma,81,0.4691,-21.05,-1705.0,-0.0414
BOTH sides × short-gamma,77,0.5065,76.09,5858.75,0.1293

## Reading

**Pre-registration:**
- Prior I (time-of-day patterns hold): PARTIAL HOLD. Opening drive Sharpe nearly identical (0.091 IS → 0.088 OOS). Afternoon_1, afternoon_2 degraded but didn't invert.
- Prior N (regime-specific asymmetry): HOLDS. Asymmetry confirmed in shorts-in-long-gamma cell (-$4,165 on 48 trades).

**Side × Regime cells (most informative result):**
- LONG × long-gamma: +$2,460 (n=33, Sharpe +0.197)
- LONG × short-gamma: +$3,724 (n=29, Sharpe +0.205)
- SHORT × long-gamma: -$4,165 (n=48, Sharpe -0.151) ← single broken cell
- SHORT × short-gamma: +$2,135 (n=48, Sharpe +0.078)

**Updated synthesis:**
Of 4 OOS stratifications today (day-of-week, VIX, time-of-day, side×regime), two inverted (day-of-week, VIX), one degraded but held direction (time-of-day), one revealed clean regime-specific asymmetry (side×regime). Strategy is NOT uniformly broken on OOS — single cell (shorts in long-gamma) is dragging total PnL while other cells stay marginally positive.

**Hypothesis (NOT filter — for future forward testing):**
- Shorts-in-long-gamma may be a real kill switch (theoretically grounded: long-gamma = dealer mean reversion)
- Test on fresh forward data when Zach's fix lands

