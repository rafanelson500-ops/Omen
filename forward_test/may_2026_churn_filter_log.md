# May 2026 OMEN forward log — churn-filter counterfactual

Generated: 2026-05-15T07:43:49
Branch: `main` (read-only on cheese/, locked config)
Source data: locked OMEN pipeline; OneMinL2 corpus_1min.parquet for churn.

## Note on simulator choice

> NOTE ON SIMULATOR CHOICE: This report uses the canonical backtest engine (cheese.backtest.run) which enforces max_concurrent_positions=1. A prior forward_test report dated 2026-05-14 (cell_breakdown.md) used a custom 1s walk-forward simulator that does NOT enforce concurrency and produced a 6-trade list including a phantom 12:40 LONG that would have been blocked live by the open 12:30 SHORT. The canonical 5-trade count in this report supersedes the prior 6-trade count for live-tradeable analysis. The cell_breakdown.md file should not be used for live-tradeable conclusions.

## Required disclosures

> (a) This is an observational forward-data log. May 2026 to date represents approximately 10 sessions, far below the 30-session minimum required by `diagnostics/forward-test-prereg/PREREG.md` for any hypothesis verdict. No statistical conclusions are drawn from this report.

> (b) The churn threshold 313.5333 e/s was derived from the IS-corpus median in the consumed-data stratification diagnostic. Applying it to forward data is exploratory only. A threshold tuned on consumed data tested against forward data is not a clean out-of-sample evaluation — it is a plausibility check.

> (c) 8 of 30 trades have NaN churn due to OneMinL2 corpus gap beyond date 2026-05-12. Those trades cannot be evaluated under the filter and are excluded from the counterfactual view but included in the full forward log.

## Step 1 — Data availability

Target window: 2026-05-01 → 2026-05-14

| date | ES bars | GEX | OneMinL2 churn |
|---|:---:|:---:|:---:|
| 2026-05-01 | ✓ | ✓ | ✓ |
| 2026-05-04 | ✓ | ✓ | ✓ |
| 2026-05-05 | ✓ | ✓ | ✓ |
| 2026-05-06 | ✓ | ✓ | ✓ |
| 2026-05-07 | ✓ | ✓ | ✓ |
| 2026-05-08 | ✓ | ✓ | ✓ |
| 2026-05-11 | ✓ | ✓ | ✓ |
| 2026-05-12 | ✓ | ✓ | ✓ |
| 2026-05-13 | ✓ | ✓ | ✗ (gap) |
| 2026-05-14 | ✓ | ✓ | ✗ (gap) |

Sessions with **ES + GEX**: **10** (2026-05-01, 2026-05-04, 2026-05-05, 2026-05-06, 2026-05-07, 2026-05-08, 2026-05-11, 2026-05-12, 2026-05-13, 2026-05-14)
OneMinL2 corpus last date: **2026-05-12**
Corpus-gap dates (no churn available): 2026-05-13, 2026-05-14

## Step 2 — Locked OMEN run summary

Config (locked, do not modify):
```
z_threshold:           1.8
stop_atr_mult:         2.0
target_atr_mult:       4.5
atr_window_bars:       14
feature_lookback_bars: 20
trail_after_r:         0
time_stop_min:         25
blackout_lunch:        True  (window [10:30, 12:30) ET)
bar_freq:              5min
```

Total May trades: **30**
Trades with churn value: **22**
Trades with NaN churn (corpus gap): **8**
Affected dates: 2026-05-13, 2026-05-14

## Step 4 — High-churn filter counterfactual

Locked split: churn_at_signal ≥ **313.5333** (IS median, not recomputed)

| Bucket | n | Total PnL | Mean PnL | Win % | Avg win | Avg loss | Exit dist |
|---|---:|---:|---:|---:|---:|---:|---|
| Full May (all trades incl NaN) | 30 | $-237.50 | $-7.92 | 60.0% | $+207.15 | $-330.52 | time=22, stop=7, target=1 |
| HIGH (churn ≥ 313.5333) | 3 | $+22.50 | $+7.50 | 66.7% | $+113.75 | $-205.00 | time=3 |
| LOW (churn < 313.5333) | 19 | $+1,423.75 | $+74.93 | 68.4% | $+243.56 | $-290.42 | time=14, stop=4, target=1 |
| NaN (excluded from filter view) | 8 | $-1,683.75 | $-210.47 | 37.5% | $+111.67 | $-403.75 | time=5, stop=3 |

**High-churn filter applied (counterfactual):** the HIGH bucket restated as the full filter view. Trades with NaN churn are excluded because the filter cannot be evaluated on them.

- n: **3**, total PnL: **$+22.50**, win rate: **66.7%**

**Low-churn filter applied (symmetry view):**

- n: **19**, total PnL: **$+1,423.75**, win rate: **68.4%**

**Context — NaN bucket carries the worst PnL of the month so far.** The 8 corpus-gap trades on 2026-05-13, 2026-05-14 total **$-1,683.75** (win rate 37.5%) — a larger drawdown than the entire HIGH+LOW evaluated set combined ($+1,446.25). Because those sessions fall beyond the OneMinL2 corpus (2026-05-12), they cannot be churn-bucketed and are excluded from the filter counterfactual while remaining in the full forward log. Any future reader should note that the filter view therefore omits the month's worst sessions.

## Step 5 — Per-trade log (full)

| date | entry_ts (ET) | dir | cell | churn_at_signal | bucket | exit | net $ | notes |
|---|---|---|---|---:|---|---|---:|---|
| 2026-05-01 | 14:35:00 | SHORT | SHORT_short | 378.55 | HIGH | time | $+195.00 |  |
| 2026-05-04 | 14:25:00 | SHORT | SHORT_short | 170.05 | LOW | time | $+82.50 |  |
| 2026-05-04 | 15:10:00 | LONG | LONG_short | 348.45 | HIGH | time | $+32.50 |  |
| 2026-05-05 | 13:15:00 | LONG | LONG_long | 154.30 | LOW | time | $+232.50 |  |
| 2026-05-05 | 13:55:00 | LONG | LONG_short | 102.75 | LOW | time | $+170.00 |  |
| 2026-05-05 | 14:50:00 | LONG | LONG_long | 91.42 | LOW | time | $+157.50 |  |
| 2026-05-05 | 15:30:00 | LONG | LONG_short | 122.97 | LOW | stop | $-273.75 |  |
| 2026-05-06 | 12:55:00 | SHORT | SHORT_short | 140.85 | LOW | stop | $-380.00 |  |
| 2026-05-06 | 14:10:00 | LONG | LONG_short | 170.65 | LOW | time | $+357.50 |  |
| 2026-05-06 | 15:05:00 | LONG | LONG_short | 248.70 | LOW | time | $+220.00 |  |
| 2026-05-07 | 14:00:00 | LONG | LONG_short | 442.07 | HIGH | time | $-205.00 |  |
| 2026-05-07 | 15:15:00 | LONG | LONG_short | 230.10 | LOW | time | $+57.50 |  |
| 2026-05-08 | 14:10:00 | SHORT | SHORT_short | 144.32 | LOW | time | $-105.00 |  |
| 2026-05-08 | 14:45:00 | SHORT | SHORT_short | 118.00 | LOW | time | $+182.50 |  |
| 2026-05-08 | 15:30:00 | SHORT | SHORT_long | 110.73 | LOW | stop | $-423.75 |  |
| 2026-05-11 | 12:45:00 | SHORT | SHORT_long | 177.58 | LOW | time | $+82.50 |  |
| 2026-05-11 | 13:15:00 | SHORT | SHORT_short | 180.48 | LOW | stop | $-392.50 |  |
| 2026-05-11 | 13:35:00 | LONG | LONG_short | 214.30 | LOW | time | $+32.50 |  |
| 2026-05-11 | 14:05:00 | LONG | LONG_short | 195.87 | LOW | time | $-167.50 |  |
| 2026-05-11 | 14:40:00 | SHORT | SHORT_short | 132.22 | LOW | target | $+751.25 |  |
| 2026-05-12 | 13:05:00 | LONG | LONG_short | 295.15 | LOW | time | $+732.50 |  |
| 2026-05-12 | 14:25:00 | LONG | LONG_short | 219.35 | LOW | time | $+107.50 |  |
| 2026-05-13 | 12:30:00 | LONG | LONG_short | NaN | NaN | time | $+57.50 | corpus gap |
| 2026-05-13 | 14:15:00 | LONG | LONG_short | NaN | NaN | time | $-155.00 | corpus gap |
| 2026-05-13 | 15:00:00 | SHORT | SHORT_short | NaN | NaN | stop | $-455.00 | corpus gap |
| 2026-05-14 | 12:30:00 | SHORT | SHORT_short | NaN | NaN | time | $+157.50 | corpus gap |
| 2026-05-14 | 13:10:00 | SHORT | SHORT_long | NaN | NaN | time | $+120.00 | corpus gap |
| 2026-05-14 | 13:50:00 | LONG | LONG_short | NaN | NaN | stop | $-680.00 | corpus gap |
| 2026-05-14 | 14:05:00 | SHORT | SHORT_short | NaN | NaN | stop | $-692.50 | corpus gap |
| 2026-05-14 | 15:30:00 | SHORT | SHORT_long | NaN | NaN | time | $-36.25 | corpus gap |

## Step 6 — Cell breakdown (context only)

| cell | n | total PnL | mean PnL | win rate |
|---|---:|---:|---:|---:|
| LONG_long | 2 | $+390.00 | $+195.00 | 100.0% |
| LONG_short | 14 | $+286.25 | $+20.45 | 64.3% |
| SHORT_long | 4 | $-257.50 | $-64.38 | 50.0% |
| SHORT_short | 10 | $-656.25 | $-65.62 | 50.0% |
