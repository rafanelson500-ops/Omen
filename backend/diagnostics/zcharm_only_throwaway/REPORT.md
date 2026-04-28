# ZCHARM-ONLY THROWAWAY DIAGNOSTIC

This is an in-sample feature-discovery test on the locked 80-session window. The result is descriptive only and does NOT validate any strategy or filter. Real validation requires forward-test data the strategy has not seen.

**Pre-registered predictions:**

- User: Sharpe 2.0 to 4.0
- Claude: Sharpe 0.3 to 1.5

## Methodology

- Window: 2025-12-26 → 2026-04-22, 5-min bars, RTH only.
- `zcharm_z` computed inline: 60-bar rolling mean/std on `feat['zcharm']` (state column from `gex.resample` `last()` aggregation), min_periods=20, std(ddof=0). Identical recipe to `features.py:79-85`.
- Long when `zcharm_z < -1.8`; short when `zcharm_z > +1.8` (fade direction matches negative correlation found in earlier diagnostic).
- Lunch blackout 10:30–12:30 ET applied identically to FlowBurstStrategy.
- All three strategies pass through the same `cheese.backtest.run()` and `BacktestConfig(bar_freq='5min')` — only signal source differs.
- random_entry uses probability=0.060 / seed=42 (calibrated for trade-count parity in prior session).


## Three-way comparison

| strategy | trades | win_rate | expectancy | total_pnl | sharpe_daily | max_drawdown | profit_factor | p_value | n_target | n_stop | n_time | n_session_close |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| flow_burst | 174 | 0.489 | $141.66 | $24,648.75 | +4.4500 | $-2,593.75 | 1.792 | 0.0032 | 15 | 42 | 112 | 5 |
| random_entry | 170 | 0.453 | $-4.78 | $-812.50 | -0.1471 | $-6,703.75 | 0.979 | 0.5414 | 6 | 35 | 129 | 0 |
| zcharm_only | 278 | 0.403 | $-56.17 | $-15,615.00 | -2.2175 | $-18,015.00 | 0.794 | 0.9382 | 13 | 99 | 156 | 10 |

## Per-regime breakdown


### flow_burst

| gamma_regime | trades | win_rate | expectancy | total |
|---|---:|---:|---:|---:|
| long | 87 | 0.460 | $124.81 | $10,858.75 |
| short | 87 | 0.517 | $158.51 | $13,790.00 |

### random_entry

| gamma_regime | trades | win_rate | expectancy | total |
|---|---:|---:|---:|---:|
| long | 87 | 0.460 | $-22.39 | $-1,947.50 |
| short | 83 | 0.446 | $13.67 | $1,135.00 |

### zcharm_only

| gamma_regime | trades | win_rate | expectancy | total |
|---|---:|---:|---:|---:|
| long | 137 | 0.438 | $14.34 | $1,965.00 |
| short | 141 | 0.369 | $-124.68 | $-17,580.00 |

## Verdict (descriptive only)

- Observed zcharm_only Sharpe = **-2.2175**
- Neither prediction covers the observed Sharpe — below Claude lower bound (0.3).
- random_entry Sharpe = -0.1471; delta zcharm_only − random_entry = -2.0704
- flow_burst Sharpe = +4.4500
- Three-way Sharpe ranking: random_entry=-0.1471  →  zcharm_only=-2.2175  →  flow_burst=+4.4500

## Plain-English summary

On the locked 80-session window with identical exit structure across all three strategies, the standalone fade-direction zcharm_z signal produced 278 trades with daily Sharpe -2.2175, expectancy $-56.17, and total PnL $-15,615.00. Compared against the random-entry sham (170 trades, Sharpe -0.1471) and flow_burst locked baseline (174 trades, Sharpe +4.4500), the zcharm-only signal sits at a different level than random and well below flow_burst. The numerical correlation found in the prior diagnostic (Spearman ρ = -0.052 at h=25 bars) does not, on its own, translate into a tradeable Sharpe through this exit structure on this in-sample window.

---

_Reminder: branch `analysis/zcharm-only-throwaway` is in-sample on the locked window and is not a deployment candidate. No filter recommendations were generated from this run._