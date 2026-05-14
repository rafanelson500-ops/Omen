# Step 3 — OPEX-week conditioning (504 trades)

Branch: `analysis/calendar-conditioning-throwaway` (throwaway).
Generated: 2026-05-14T13:06:09

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

## OPEX-week definition

- **OPEX week** = the Monday-Friday calendar week containing the 
  third Friday of each calendar month.
- Computed programmatically: first day of month → add days to first 
  Friday → add 14 days = third Friday → Monday of that week is third_friday − 4 days.
- A trade is `is_opex_week=True` iff its session date is one of the 
  5 weekdays (Mon-Fri) of that OPEX week.

## Coverage

- OPEX-week trades    : **135** (26.8%)
- Non-OPEX trades     : **369** (73.2%)
- Unique OPEX dates with trades: **36**
- Third Fridays in trade range : **8** (2025-09-19 → 2026-04-17)

## Group metrics

| group | N | sum $ | win | avg win | avg loss | PF | Sharpe (ann.) | max DD |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| A: All 504 trades | 504 | $+14186 | 47.4% | $+423.19 | $-328.14 | 1.16 | +1.63 | $-6719 |
| B: OPEX week trades | 135 | $+10094 | 51.9% | $+472.32 | $-353.37 | 1.44 | +4.30 | $-2909 |
| C: Non-OPEX week trades | 369 | $+4092 | 45.8% | $+402.84 | $-319.94 | 1.06 | +0.64 | $-6021 |
| D: minus-SL ∩ OPEX week | 99 | $+5011 | 48.5% | $+484.58 | $-357.82 | 1.27 | +2.49 | $-2339 |

⚠ flag = N < 30, insufficient sample.

