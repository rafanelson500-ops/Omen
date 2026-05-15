# Blackout-window discrepancy — IS counterfactual

Generated: 2026-05-14T23:49:51
Branch: `diagnostics/blackout-window-discrepancy`

## Setup

- IS corpus: **2025-12-26 → 2026-04-22** (80 sessions)
- Locked baseline params held in both runs: `z_threshold=1.8`, `bar_freq=5min`, `blackout_lunch=True`, `stop=2.0×ATR`, `target=4.5×ATR`, `time_stop=25min`, `atr_window=14`, `feature_lookback=20`, `trail_after_r=0`.
- Single variable: blackout window.
  - **Run A**: locked code, `[10:30, 12:30)` ET
  - **Run B**: temporarily edited code, `[12:00, 13:00)` ET
- Both runs against the same feature frame (80 sessions).

## Headline metrics

| Metric           |  Run A (10:30-12:30)|  Run B (12:00-13:00)|    Delta (B-A)|
|------------------|---------------------|---------------------|---------------|
| Trade count      |                  268|                  290|            +22|
| Total PnL        |          $+13,028.75|          $+13,293.75|       $+265.00|
| Win rate         |                50.4%|                51.0%|       +0.66 pp|
| Mean PnL/trade   |              $+48.61|              $+45.84|         $-2.77|
| Avg win          |             $+443.33|             $+438.07|         $-5.26|
| Avg loss         |             $-352.04|             $-362.97|        $-10.93|
| Profit factor    |                1.278|                1.258|         -0.020|
| Sharpe           |               +2.351|               +2.336|         -0.015|
| Max DD           |           $-3,638.75|           $-5,472.50|     $-1,833.75|

## Exit distribution

| exit | Run A | Run B | Delta |
|---|---:|---:|---:|
| stop | 50 | 52 | +2 |
| target | 11 | 11 | +0 |
| time | 207 | 227 | +20 |

## Per-cell breakdown

| cell | A: n | A: total $ | A: win | B: n | B: total $ | B: win | Δ n | Δ total $ |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| LONG_long | 73 | $+3,178.75 | 49.3% | 78 | $+1,666.25 | 51.3% | +5 | $-1,512.50 |
| LONG_short | 68 | $+5,597.50 | 48.5% | 75 | $+6,900.00 | 49.3% | +7 | $+1,302.50 |
| SHORT_long | 66 | $+7,095.00 | 62.1% | 64 | $+3,980.00 | 57.8% | -2 | $-3,115.00 |
| SHORT_short | 61 | $-2,842.50 | 41.0% | 73 | $+747.50 | 46.6% | +12 | $+3,590.00 |

## Delta analysis

- Trades present in **both** runs (entry_time match): **238**
- Trades **unique to Run A** (locked allows 12:30-12:55 signals that B blocks): **30**
- Trades **unique to Run B** (documented allows 10:30-11:55 signals that A blocks): **52**

### New trades unlocked by Run B (10:30-12:00 signals allowed)

- n: **52**
- total net: **$+2,402.50**
- win rate: **57.7%**
- cell distribution: LONG_long=11, LONG_short=17, SHORT_long=8, SHORT_short=16

| # | entry_time | side | gamma_regime | cell | exit | bars | net $ |
|---|---|---|---|---|---|---:|---:|
| 1 | 2025-12-29 11:15:00-0500 | LONG | long | LONG_long | time | 5 | $-317.50 |
| 2 | 2025-12-29 11:50:00-0500 | LONG | short | LONG_short | time | 5 | $-130.00 |
| 3 | 2025-12-30 11:35:00-0500 | SHORT | short | SHORT_short | time | 5 | $+432.50 |
| 4 | 2026-01-05 11:25:00-0500 | LONG | short | LONG_short | time | 5 | $+245.00 |
| 5 | 2026-01-07 11:45:00-0500 | LONG | short | LONG_short | time | 5 | $+307.50 |
| 6 | 2026-01-08 11:10:00-0500 | SHORT | short | SHORT_short | time | 5 | $-30.00 |
| 7 | 2026-01-09 11:50:00-0500 | LONG | short | LONG_short | time | 5 | $+245.00 |
| 8 | 2026-01-12 11:50:00-0500 | LONG | short | LONG_short | time | 5 | $-42.50 |
| 9 | 2026-01-13 11:35:00-0500 | LONG | long | LONG_long | time | 5 | $+432.50 |
| 10 | 2026-01-14 11:25:00-0500 | LONG | long | LONG_long | stop | 4 | $-880.00 |
| 11 | 2026-01-16 11:10:00-0500 | LONG | long | LONG_long | time | 5 | $+120.00 |
| 12 | 2026-01-20 11:25:00-0500 | SHORT | short | SHORT_short | time | 5 | $-317.50 |
| 13 | 2026-01-23 11:30:00-0500 | SHORT | long | SHORT_long | time | 5 | $+7.50 |
| 14 | 2026-01-27 11:30:00-0500 | SHORT | short | SHORT_short | time | 5 | $+32.50 |
| 15 | 2026-01-28 11:35:00-0500 | SHORT | short | SHORT_short | time | 5 | $+320.00 |
| 16 | 2026-01-29 11:15:00-0500 | LONG | short | LONG_short | time | 5 | $+320.00 |
| 17 | 2026-02-02 13:00:00-0500 | SHORT | short | SHORT_short | time | 5 | $+170.00 |
| 18 | 2026-02-04 11:20:00-0500 | SHORT | short | SHORT_short | time | 5 | $+682.50 |
| 19 | 2026-02-05 11:20:00-0500 | LONG | long | LONG_long | time | 5 | $+807.50 |
| 20 | 2026-02-06 11:55:00-0500 | LONG | short | LONG_short | time | 5 | $+95.00 |
| 21 | 2026-02-09 11:10:00-0500 | SHORT | short | SHORT_short | time | 5 | $-217.50 |
| 22 | 2026-02-09 11:55:00-0500 | LONG | long | LONG_long | time | 5 | $+57.50 |
| 23 | 2026-02-12 11:10:00-0500 | SHORT | short | SHORT_short | time | 5 | $+1,257.50 |
| 24 | 2026-02-17 13:00:00-0500 | LONG | long | LONG_long | time | 5 | $+445.00 |
| 25 | 2026-02-19 11:45:00-0500 | SHORT | short | SHORT_short | time | 5 | $+282.50 |
| 26 | 2026-02-20 11:35:00-0500 | LONG | long | LONG_long | time | 5 | $+682.50 |
| 27 | 2026-02-25 11:25:00-0500 | LONG | short | LONG_short | time | 5 | $+545.00 |
| 28 | 2026-02-25 11:50:00-0500 | LONG | long | LONG_long | time | 5 | $+20.00 |
| 29 | 2026-02-27 11:55:00-0500 | LONG | short | LONG_short | time | 5 | $-705.00 |
| 30 | 2026-03-02 11:10:00-0500 | LONG | long | LONG_long | stop | 3 | $-1,305.00 |
| 31 | 2026-03-02 11:30:00-0500 | SHORT | short | SHORT_short | stop | 2 | $-1,155.00 |
| 32 | 2026-03-02 11:45:00-0500 | LONG | short | LONG_short | time | 5 | $-167.50 |
| 33 | 2026-03-04 11:15:00-0500 | SHORT | long | SHORT_long | time | 5 | $-242.50 |
| 34 | 2026-03-10 11:10:00-0400 | SHORT | long | SHORT_long | time | 5 | $+7.50 |
| 35 | 2026-03-10 11:35:00-0400 | SHORT | long | SHORT_long | time | 5 | $-392.50 |
| 36 | 2026-03-12 11:40:00-0400 | LONG | short | LONG_short | time | 5 | $+70.00 |
| 37 | 2026-03-16 11:55:00-0400 | SHORT | long | SHORT_long | time | 5 | $+370.00 |
| 38 | 2026-03-19 11:20:00-0400 | SHORT | short | SHORT_short | time | 5 | $+807.50 |
| 39 | 2026-03-19 13:05:00-0400 | SHORT | long | SHORT_long | time | 5 | $-355.00 |
| 40 | 2026-03-25 11:10:00-0400 | SHORT | short | SHORT_short | time | 5 | $-305.00 |
| 41 | 2026-03-25 11:40:00-0400 | SHORT | long | SHORT_long | time | 5 | $+95.00 |
| 42 | 2026-03-31 11:15:00-0400 | LONG | short | LONG_short | time | 5 | $-605.00 |
| 43 | 2026-04-07 11:20:00-0400 | LONG | short | LONG_short | time | 5 | $-142.50 |
| 44 | 2026-04-08 11:15:00-0400 | LONG | short | LONG_short | time | 5 | $+532.50 |
| 45 | 2026-04-09 11:15:00-0400 | LONG | short | LONG_short | time | 5 | $+757.50 |
| 46 | 2026-04-10 11:30:00-0400 | SHORT | short | SHORT_short | time | 5 | $+745.00 |
| 47 | 2026-04-13 11:40:00-0400 | LONG | long | LONG_long | time | 5 | $-392.50 |
| 48 | 2026-04-14 11:10:00-0400 | SHORT | short | SHORT_short | stop | 2 | $-505.00 |
| 49 | 2026-04-14 11:25:00-0400 | LONG | short | LONG_short | time | 5 | $+495.00 |
| 50 | 2026-04-15 11:15:00-0400 | LONG | short | LONG_short | time | 5 | $-130.00 |
| 51 | 2026-04-15 11:40:00-0400 | SHORT | short | SHORT_short | time | 5 | $-17.50 |
| 52 | 2026-04-16 11:30:00-0400 | SHORT | long | SHORT_long | stop | 1 | $-630.00 |

### Trades suppressed by Run B (12:30-12:55 signals blocked)

- n: **30**
- total net: **$+2,137.50**
- win rate: **56.7%**
- cell distribution: LONG_long=6, LONG_short=10, SHORT_long=10, SHORT_short=4

| # | entry_time | side | gamma_regime | cell | exit | bars | net $ |
|---|---|---|---|---|---|---:|---:|
| 1 | 2025-12-26 12:30:00-0500 | LONG | long | LONG_long | stop | 1 | $-292.50 |
| 2 | 2025-12-29 12:55:00-0500 | LONG | short | LONG_short | time | 5 | $+132.50 |
| 3 | 2025-12-30 12:35:00-0500 | LONG | short | LONG_short | time | 5 | $-17.50 |
| 4 | 2026-01-05 12:40:00-0500 | LONG | short | LONG_short | time | 5 | $+45.00 |
| 5 | 2026-01-07 12:55:00-0500 | SHORT | long | SHORT_long | time | 5 | $+320.00 |
| 6 | 2026-01-14 12:35:00-0500 | SHORT | short | SHORT_short | time | 5 | $-142.50 |
| 7 | 2026-01-15 12:30:00-0500 | SHORT | long | SHORT_long | time | 5 | $+7.50 |
| 8 | 2026-01-22 12:35:00-0500 | LONG | short | LONG_short | time | 5 | $+45.00 |
| 9 | 2026-01-23 12:35:00-0500 | SHORT | long | SHORT_long | time | 5 | $+895.00 |
| 10 | 2026-01-27 12:30:00-0500 | LONG | short | LONG_short | time | 5 | $-205.00 |
| 11 | 2026-01-29 12:55:00-0500 | SHORT | long | SHORT_long | stop | 2 | $-867.50 |
| 12 | 2026-01-30 12:30:00-0500 | LONG | short | LONG_short | time | 5 | $-530.00 |
| 13 | 2026-02-02 12:55:00-0500 | LONG | short | LONG_short | time | 5 | $-330.00 |
| 14 | 2026-02-03 12:30:00-0500 | SHORT | long | SHORT_long | time | 5 | $+420.00 |
| 15 | 2026-02-04 12:30:00-0500 | SHORT | long | SHORT_long | time | 5 | $+132.50 |
| 16 | 2026-02-06 12:30:00-0500 | LONG | short | LONG_short | time | 5 | $+245.00 |
| 17 | 2026-02-17 12:45:00-0500 | SHORT | long | SHORT_long | time | 5 | $-217.50 |
| 18 | 2026-02-19 12:50:00-0500 | SHORT | short | SHORT_short | time | 5 | $-280.00 |
| 19 | 2026-02-20 12:35:00-0500 | LONG | short | LONG_short | time | 5 | $+795.00 |
| 20 | 2026-03-03 12:35:00-0500 | SHORT | short | SHORT_short | time | 5 | $-580.00 |
| 21 | 2026-03-10 12:35:00-0400 | LONG | long | LONG_long | time | 5 | $+7.50 |
| 22 | 2026-03-11 12:35:00-0400 | LONG | short | LONG_short | time | 5 | $+207.50 |
| 23 | 2026-03-19 12:50:00-0400 | SHORT | long | SHORT_long | time | 5 | $+807.50 |
| 24 | 2026-03-19 13:20:00-0400 | LONG | long | LONG_long | time | 5 | $-130.00 |
| 25 | 2026-03-24 12:40:00-0400 | SHORT | long | SHORT_long | time | 5 | $+370.00 |
| 26 | 2026-03-31 12:40:00-0400 | LONG | long | LONG_long | time | 5 | $+1,532.50 |
| 27 | 2026-04-02 12:45:00-0400 | LONG | long | LONG_long | time | 5 | $-267.50 |
| 28 | 2026-04-13 12:30:00-0400 | LONG | long | LONG_long | time | 5 | $+332.50 |
| 29 | 2026-04-15 12:45:00-0400 | SHORT | short | SHORT_short | stop | 4 | $-405.00 |
| 30 | 2026-04-16 12:35:00-0400 | SHORT | long | SHORT_long | time | 5 | $+107.50 |

## Disclosure

> This is a consumed-data counterfactual on the IS corpus. 
> Run A reflects the locked code window (always [10:30, 12:30)). 
> Run B tests the documented window (12:00-13:00) which has 
> never run in code. Neither run authorizes a config change. 
> strategy.py was temporarily modified for Run B and has been 
> reverted. git diff backend/cheese/strategy.py confirms zero 
> diff post-revert.
