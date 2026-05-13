# OMEN-minus-SL 9-session pulse (May 12 included) — THROWAWAY

Branch: `analysis/omen-minus-sl-may12-pulse-throwaway` (throwaway / archive only; never merges to main).
Generated: 2026-05-13T10:04:02

## 1. Disclosure

## DISCLOSURE — partially-consumed pool, pulse only

These 9 fresh sessions have been used for multiple prior analyses
(original quick-check, ATR=20 variant, Zach May params, bugfixed
re-run). Adding May 12 is a 9th-session extension of an already-
consumed pool. Cumulatively biased.

Sample size remains far too small for any verdict. The locked
pre-registered forward test (commit `9c1c22f`) requires 30+ fresh
sessions and has not yet been triggered.


## 2. Setup

- Fresh sessions: **9** (2026-04-30 → 2026-05-12).
- Bugfixed infrastructure on main (features.py session-boundary fix + backtest.py time-stop + overlap fixes).
- Locked baseline params unchanged: z=1.8, blackout_lunch=True, stop=2.0×ATR, target=4.5×ATR, time_stop=25min, ATR=14, bar_freq=5min.
- ES 1s sources: 3 parquet files concatenated in-memory (primary 9/8→4/27, data-refresh 4/28→5/11, May 12 single-day pull).

## 3. 9-session metrics

| arm | N | win | mean $ | sum $ | Sharpe | max DD |
|---|---:|---:|---:|---:|---:|---:|
| full_omen_bugfixed | 26 | 65.4% | $+45.72 | $+1189 | +3.74 | $-914 |
| omen_minus_sl_bugfixed | 24 | 66.7% | $+63.75 | $+1530 | +5.02 | $-914 |

### Per-cell breakdown

| cell | N | mean $ | sum $ | Sharpe (if N≥10) |
|---|---:|---:|---:|---:|
| LONG_long | 3 | $+274.17 | $+822 | (n<10: n=3) |
| LONG_short | 11 | $+134.77 | $+1482 | +8.89 |
| SHORT_long | 2 | $-170.62 | $-341 | (n<10: n=2) |
| SHORT_short | 10 | $-77.50 | $-775 | -3.34 |

### Exit-reason distribution

| exit_reason | count |
|---|---:|
| time | 20 |
| stop | 5 |
| target | 1 |
| trail | 0 |
| session_close | 0 |

## 4. Comparison: 8-session bugfixed vs 9-session (this pulse)

| metric | 8-session (bugfixed) | 9-session (this) | Δ |
|---|---:|---:|---:|
| Full OMEN N | 24 | 26 | +2 |
| Full OMEN win rate | 62.5% | 65.4% | +2.9 pp |
| Full OMEN mean $ | $+14.53 | $+45.72 | $+31.19 |
| Full OMEN sum $ | $+349 | $+1189 | $+840 |
| **Full OMEN Sharpe** | **+1.28** | **+3.74** | **+2.46** |
| Minus-SL N | 22 | 24 | +2 |
| Minus-SL mean $ | $+31.36 | $+63.75 | $+32.39 |
| Minus-SL sum $ | $+690 | $+1530 | $+840 |
| **Minus-SL Sharpe** | **+2.66** | **+5.02** | **+2.36** |
| SHORT_long N | 2 | 2 | +0 |
| SHORT_long sum $ | $-341 | $-341 | $-0 |

## 5. May 12 trade detail

May 12 contributed **2 trade(s)**, total net = **$+840.00**.

| entry_time ET | side | gamma_regime | entry $ | exit $ | exit_reason | bars held | net $ |
|---|---|---|---:|---:|---|---:|---:|
| 13:05 | LONG | short | $7373.88 | $7388.62 | time | 5 | $+732.50 |
| 14:25 | LONG | short | $7403.38 | $7405.62 | time | 5 | $+107.50 |

May 12 cells: LONG_short×2.

## 6. Per-session pulse table

| session | N trades | net $ |
|---|---:|---:|
| 2026-04-30 | 2 | $+102.50 |
| 2026-05-01 | 2 | $-360.00 |
| 2026-05-04 | 3 | $-108.75 |
| 2026-05-05 | 5 | $+500.00 |
| 2026-05-06 | 3 | $+197.50 |
| 2026-05-07 | 1 | $+57.50 |
| 2026-05-08 | 3 | $-346.25 |
| 2026-05-11 | 5 | $+306.25 |
| 2026-05-12 | 2 | $+840.00 |
| **TOTAL** | **26** | **$+1188.75** |

## 7. Honest note

This is **a pulse, not validation**. The 9-session sample is the 5th analysis touching this fresh-session pool (original quick-check, 
ATR=20 variant, Zach May, bugfixed re-run, this May-12 extension). The data is 
cumulatively biased.

The pre-registered forward test (`9c1c22f`) requires **≥ 30 fresh sessions** 
for a verdict on the OMEN-minus-SL hypothesis. Current accumulated session 
count is **9 / 30** (30% of the required minimum).

Pulse readings (e.g., minus-SL Sharpe > full Sharpe persisting from 8 to 9 
sessions) are **directionally interesting** but cannot establish the 
hypothesis. The pulse continues, the pre-reg holds.

