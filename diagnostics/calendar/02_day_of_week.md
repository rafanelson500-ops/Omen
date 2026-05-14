# Step 2 — day-of-week conditioning (504 trades)

Branch: `analysis/calendar-conditioning-throwaway` (throwaway).
Generated: 2026-05-14T13:05:41

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

## Weekday counts

| weekday | N | flag |
|---|---:|---|
| Monday | 104 |  |
| Tuesday | 110 |  |
| Wednesday | 107 |  |
| Thursday | 99 |  |
| Friday | 84 |  |

## Group metrics

| group | N | sum $ | win | avg win | avg loss | PF | Sharpe (ann.) | max DD |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| A: All 504 trades | 504 | $+14186 | 47.4% | $+423.19 | $-328.14 | 1.16 | +1.63 | $-6719 |
| B: Monday | 104 | $+30 | 41.3% | $+385.12 | $-270.98 | 1.00 | +0.02 | $-3756 |
| C: Tuesday | 110 | $-1300 | 44.5% | $+334.03 | $-289.63 | 0.93 | -0.82 | $-3708 |
| D: Wednesday | 107 | $+3121 | 54.2% | $+390.04 | $-397.98 | 1.16 | +1.64 | $-7456 |
| E: Thursday | 99 | $+392 | 43.4% | $+473.92 | $-356.90 | 1.02 | +0.23 | $-4106 |
| F: Friday | 84 | $+11942 | 54.8% | $+548.12 | $-349.24 | 1.90 | +6.90 | $-2236 |
| G: minus-SL ∩ Monday | 80 | $+788 | 42.5% | $+333.97 | $-229.73 | 1.07 | +0.60 | $-3638 |
| H: minus-SL ∩ Friday | 65 | $+9675 | 53.8% | $+556.79 | $-327.08 | 1.99 | +6.42 | $-3019 |

⚠ flag = N < 30, insufficient sample.

