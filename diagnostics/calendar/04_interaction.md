# Step 4 — interaction: minus-SL × OPEX × LATE (single locked test)

Branch: `analysis/calendar-conditioning-throwaway` (throwaway).
Generated: 2026-05-14T13:06:32

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

## Locked spec

- Single interaction test. No other interactions explored.
- Cell exclusion: SHORT_long removed.
- LATE bucket: 15:30 ≤ entry < 15:55 (matches Step 1 definition).
- OPEX week: Mon-Fri containing the third Friday of the month (matches Step 3 definition).

## Group metrics

| group | N | sum $ | win | avg win | avg loss | PF | Sharpe (ann.) | max DD |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| A: minus-SL ∩ OPEX week ∩ LATE ⚠ | 4 | $+380 | 50.0% | $+338.75 | $-148.75 | 2.28 | +3.83 | $-236 |
| B: minus-SL ∩ non-OPEX ∩ LATE ⚠ | 5 | $+2556 | 80.0% | $+679.38 | $-161.25 | 16.85 | +15.98 | $-161 |

⚠ flag = N < 30, insufficient sample.

## ⚠ Insufficient samples

- **A: minus-SL ∩ OPEX week ∩ LATE** has N = 4 (< 30). Treat as suggestive only.
- **B: minus-SL ∩ non-OPEX ∩ LATE** has N = 5 (< 30). Treat as suggestive only.

