# Step 1 — time-of-day conditioning (504 trades)

Branch: `analysis/calendar-conditioning-throwaway` (throwaway).
Generated: 2026-05-14T13:05:09

## Disclosure

```
This analysis is exploratory diagnostic work on a heavily consumed
corpus during an active forward test. It is NOT pre-registered.
Results CANNOT authorize modifications to OMEN's locked config or
pre-reg.

This is approximately the Nth diagnostic on this 504-trade corpus.
Project-wide false discovery rate is high. Time-of-day and OPEX
buckets are correlated with vol regime, so positive findings here
may overlap with the ATR/VIX regime findings from prior work
(commit b8880d6).

Any positive finding can only be honestly evaluated on a future
pre-registered forward window after OMEN-minus-SL verdict.

```

## LOCKED time buckets

- **MORNING**:   09:30 ≤ entry < 11:00
- **MIDDAY**:    11:00 ≤ entry < 13:00 (effectively 11:00-12:00; 12:00-13:00 already blacked out by OMEN's lunch filter)
- **AFTERNOON**: 13:00 ≤ entry < 15:30
- **LATE**:      15:30 ≤ entry < 15:55

## Bucket counts

| bucket | N | flag |
|---|---:|---|
| MORNING | 76 |  |
| MIDDAY | 55 |  |
| AFTERNOON | 362 |  |
| LATE | 11 | ⚠ N < 30 |
| OUT_OF_RANGE | 0 |  |

## Group metrics

| group | N | sum $ | win | avg win | avg loss | PF | Sharpe (ann.) | max DD |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| A: All 504 trades | 504 | $+14186 | 47.4% | $+423.19 | $-328.14 | 1.16 | +1.63 | $-6719 |
| B: MORNING (09:30-11:00) | 76 | $+4245 | 43.4% | $+761.10 | $-485.38 | 1.20 | +1.20 | $-4111 |
| C: MIDDAY  (11:00-13:00) | 55 | $+2969 | 52.7% | $+415.26 | $-348.99 | 1.33 | +1.65 | $-2459 |
| D: AFTERNOON (13:00-15:30) | 362 | $+4371 | 47.0% | $+355.44 | $-291.95 | 1.08 | +0.70 | $-5614 |
| E: LATE      (15:30-15:55) ⚠ | 11 | $+2601 | 63.6% | $+508.39 | $-239.38 | 3.72 | +7.51 | $-236 |
| F: minus-SL ∩ MORNING | 50 | $+4412 | 42.0% | $+862.56 | $-472.46 | 1.32 | +1.82 | $-3244 |
| G: minus-SL ∩ AFTERNOON | 273 | $+5216 | 46.5% | $+367.19 | $-283.68 | 1.13 | +0.99 | $-3879 |
| H: minus-SL ∩ LATE ⚠ | 9 | $+2936 | 66.7% | $+565.83 | $-152.92 | 7.40 | +10.68 | $-236 |

⚠ flag = N < 30, insufficient sample.

