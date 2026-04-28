# Time-of-day stratification — Flow Burst locked baseline

## Summary

On 174 trades from the locked Dec 2025 – Apr 2026 baseline, the opening-drive bucket (09:30–09:59) holds **n=39** trades with mean P&L **$78.65** and total **$3,067.50**. The closing-drive bucket (15:30–16:00) holds **n=5** trades with mean P&L **$306.25** and total **$1,531.25**.

## Buckets

| bucket | window | n | win_rate | mean_pnl | median_pnl | total_pnl | n_target | n_stop | n_time | per_trade_sharpe | low_confidence |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| opening_drive | 09:30-09:59 | 39 | 0.462 | $78.65 | $-292.50 | $3,067.50 | 8 | 19 | 12 | +0.0906 | no |
| morning_2 | 10:00-10:29 | 1 | 0.000 | $-205.00 | $-205.00 | $-205.00 | 0 | 0 | 1 | — | yes |
| lunch | 10:30-12:29 | 0 | — | — | — | $0.00 | 0 | 0 | 0 | — | yes |
| afternoon_1 | 12:30-13:59 | 22 | 0.500 | $255.23 | $57.50 | $5,615.00 | 2 | 0 | 20 | +0.5205 | no |
| afternoon_2 | 14:00-15:29 | 107 | 0.495 | $136.82 | $-5.00 | $14,640.00 | 5 | 23 | 79 | +0.2321 | no |
| closing_drive | 15:30-16:00 | 5 | 0.600 | $306.25 | $101.25 | $1,531.25 | 0 | 0 | 0 | +0.6303 | yes |

## Closing drive — sub-stratified by gamma regime

| bucket | window | n | win_rate | mean_pnl | median_pnl | total_pnl | n_target | n_stop | n_time | per_trade_sharpe | low_confidence |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| closing_drive::long_gamma | 15:30-16:00 | 2 | 0.000 | $-111.25 | $-111.25 | $-222.50 | 0 | 0 | 0 | -1.5733 | yes |
| closing_drive::short_gamma | 15:30-16:00 | 3 | 1.000 | $584.58 | $763.75 | $1,753.75 | 0 | 0 | 0 | +1.3813 | yes |

## Comparison vs literature prediction

Baltussen et al (2021) and Gao, Han, Li, Zhou (2018) document a **U-shaped intraday momentum profile** in equity index futures: an opening-drive peak (driven by overnight information assimilation and dealer hedging at the open), a midday lull, and a **closing-drive peak** in the last 30 minutes (driven by late-day rebalancing and end-of-day delta hedging by option dealers). The hypothesis under test: the Flow Burst signal — which keys off `gexoflow_z` / `dexoflow_z` z-score spikes — should also show elevated expectancy in the 15:30–16:00 closing-drive window if the underlying flow signal captures dealer-hedging activity, not just open-drive information flow.

**Observed:**  opening_drive n=39, mean $78.65; closing_drive n=5, mean $306.25.


## Verdict: **INCONCLUSIVE**

Closing-drive bucket has n=5 (< 10); too few trades to confirm or kill the closing-drive hypothesis. Observed mean P&L in closing_drive = $306.25 vs opening_drive $78.65 (ratio 3.89), but at this sample size the standard error is dominant.


Low-confidence flag threshold: any bucket with n < 10 is marked `low_confidence: yes` in the tables and should not be used for inference.
