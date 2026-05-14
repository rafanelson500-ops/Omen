# Step 2 — VIX-conditioned analysis (504 trades)

Branch: `analysis/vol-regime-conditioning-throwaway` (throwaway).
Generated: 2026-05-14T12:55:00

## Disclosure

```
This analysis is exploratory diagnostic work on a heavily consumed
corpus during an active forward test. It is NOT pre-registered.
Results CANNOT authorize any modification to locked OMEN config
or pre-reg.

The 504-trade all-bugfixes corpus has been examined many times
across multiple diagnostics. Project-wide false discovery rate is
high. Any positive finding here can only be honestly evaluated on
a future pre-registered forward window after OMEN-minus-SL verdict.

```

## VIX caveat

```
VIX is daily close — session-level granularity only. Not intraday
vol state at entry. ATR conditioning is more directly relevant for
a 25-minute ES hold. VIX results are a cross-asset regime check,
not a within-instrument vol measure.

```

## Setup

- Trade pool: **504 trades**, **146 sessions**, 2025-09-08 → 2026-04-21.
- VIX source: `backend/data/analysis/vix_daily_full.csv` (CBOE public CSV, 175 rows, range 2025-09-08 → 2026-05-13).
- Join: on session date. VIX close from the trade's session date.

## Eligibility

- Eligible : **504**
- Excluded : **0** (VIX unavailable for session)

## VIX distribution (eligible)

- n      : 504
- min    : 14.00
- p25    : 16.18
- median : 17.51
- p75    : 20.52
- max    : 31.05

## Tercile boundaries (LOCKED for future pre-reg)

- `low_vix_boundary`  (33rd pct) = **16.4800**
- `high_vix_boundary` (67th pct) = **19.4900**

## Group metrics

| group | N | sum $ | win | avg win | avg loss | PF | Sharpe (ann.) | max DD |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| A: All 504 trades (incl. excluded) | 504 | $+14186 | 47.4% | $+423.19 | $-328.14 | 1.16 | +1.63 | $-6719 |
| B: Low-VIX (eligible) | 170 | $-2975 | 47.6% | $+248.78 | $-259.85 | 0.87 | -1.54 | $-4114 |
| C: Mid-VIX (eligible) | 167 | $+11546 | 49.7% | $+447.79 | $-305.00 | 1.45 | +3.81 | $-4101 |
| D: High-VIX (eligible) | 167 | $+5615 | 44.9% | $+584.33 | $-415.33 | 1.15 | +1.57 | $-4148 |
| E: minus-SL ∩ Low-VIX | 130 | $-2044 | 46.9% | $+231.78 | $-234.53 | 0.87 | -1.37 | $-4368 |
| F: minus-SL ∩ High-VIX | 125 | $+3281 | 42.4% | $+633.56 | $-420.80 | 1.11 | +1.07 | $-3509 |

