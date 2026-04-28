# VIX-regime stratification — Flow Burst locked baseline

## Summary

On 174 trades over 80 sessions (Dec 2025 – Apr 2026), VIX daily closes ranged 13.60 – 31.05 (mean 20.16, median 19.36). After joining each trade to the prior trading day's VIX close and bucketing into five literature-standard regimes, the highest-Sharpe bucket above the n≥15 confidence floor is the **elevated** bucket [20.00, 25.00) (n=40, per-trade Sharpe +0.5744, mean $450.16). The strategy's overall per-trade Sharpe is +0.2193 on mean P&L $141.66.

## VIX distribution across the 80-day window

| stat | value |
|---|---:|
| min | 13.60 |
| 25th pct | 16.65 |
| median | 19.36 |
| mean | 20.16 |
| 75th pct | 23.78 |
| max | 31.05 |
| trading days | 80 |

## Per-bucket performance

| bucket | range | n | n_distinct_days | win_rate | mean_pnl | median_pnl | total_pnl | per_trade_sharpe | n_target | n_stop | n_time | n_session_close | low_conf |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| low | [−∞, 15.00) | 21 | 7 | 0.333 | $9.29 | $-80.00 | $195.00 | +0.0248 | 2 | 7 | 12 | 0 | no |
| low_mid | [15.00, 18.00) | 55 | 22 | 0.400 | $38.75 | $-61.25 | $2,131.25 | +0.0770 | 4 | 14 | 34 | 3 | no |
| mid | [18.00, 20.00) | 29 | 13 | 0.448 | $16.77 | $-42.50 | $486.25 | +0.0335 | 0 | 9 | 20 | 0 | no |
| elevated | [20.00, 25.00) | 40 | 18 | 0.725 | $450.16 | $423.12 | $18,006.25 | +0.5744 | 4 | 6 | 28 | 2 | no |
| high | [25.00, +∞) | 29 | 13 | 0.483 | $132.07 | $-17.50 | $3,830.00 | +0.1581 | 5 | 6 | 18 | 0 | no |

## Pre-registered hypothesis verdicts

### Hypothesis A — edge concentrates in low VIX (<18)

**Verdict: CONTRADICTED**

Low-VIX (<18) mean P&L $30.61 on n=76 is materially below overall $141.66 (<75% of overall).


### Hypothesis D — edge concentrates in middle VIX (15-20)

**Verdict: CONTRADICTED**

Mid-VIX (15-20) mean P&L $31.16 on n=84 is materially below overall $141.66 (<75% of overall).


## Caveats

- VIX is taken as the daily close on the trading day **prior** to entry (value known at the trade-day's open). Daily resolution does **not** capture intraday VIX spikes that may occur during a session.
- The 80-day window may not span all VIX environments. Buckets that did not appear (e.g. `low <15`, `high ≥25`) cannot be evaluated regardless of any verdict logic. Any verdict here is bounded by the VIX range that actually appeared in this window.
- Per-bucket Sharpe at small n is high-variance. Buckets with n < 15 are flagged `low_conf: yes` and should be treated as exploratory only.
- This is descriptive analysis. No filter recommendations are made.
