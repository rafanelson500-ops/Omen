# Step 1 — ATR-conditioned analysis (504 trades)

Branch: `analysis/vol-regime-conditioning-throwaway` (throwaway).
Generated: 2026-05-14T12:53:33

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

## Setup

- Trade pool: **504 trades** (IS=257, OOS=247), **146 sessions**, 2025-09-08 → 2026-04-21.
- ATR formula: `tr.rolling(14, min_periods=5).mean()` per session — replicated from `features.py` (read-only).
- Baseline: `atr14.rolling(60, min_periods=20).mean()` per session.
- Baseline lookup at bar **immediately preceding entry** (entry_time − 5 min), same-session only.

## Eligibility

- Eligible : **428**
- Excluded : **76**
  - no same-session prior bar : 76
  - < 20 prior bars in session: 0

## ATR sanity (recomputed vs logged `atr_at_entry`)

- median |Δ| = 0.178571
- 95th pct  = 1.017857
- max       = 3.321429

(`atr_ratio` numerator uses the trade log's logged `atr_at_entry`, i.e. the value OMEN actually sized exits with.)

## `atr_ratio` distribution (eligible trades)

- n           : 428
- min         : 0.4086
- p25         : 0.6386
- median      : 0.7309
- p75         : 0.8627
- max         : 4.0708

## Tercile boundaries (LOCKED for future pre-reg)

- `low_ratio_boundary`  (33rd pct of eligible) = **0.670724**
- `high_ratio_boundary` (67th pct of eligible) = **0.801352**

## Group metrics

| group | N | sum $ | win | avg win | avg loss | PF | Sharpe (ann.) | max DD |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| A: All 504 trades (incl. excluded) | 504 | $+14186 | 47.4% | $+423.19 | $-328.14 | 1.16 | +1.63 | $-6719 |
| B: Low-ATR regime (eligible) | 143 | $-1784 | 44.1% | $+282.60 | $-244.84 | 0.91 | -0.75 | $-5054 |
| C: Mid-ATR regime (eligible) | 142 | $+11578 | 53.5% | $+387.43 | $-270.72 | 1.65 | +3.85 | $-1590 |
| D: High-ATR regime (eligible) | 143 | $+148 | 46.9% | $+429.51 | $-376.71 | 1.01 | +0.04 | $-9435 |
| E: minus-SL ∩ Low-ATR | 98 | $-5152 | 37.8% | $+263.75 | $-244.45 | 0.65 | -3.16 | $-6544 |
| F: minus-SL ∩ High-ATR | 113 | $+7035 | 51.3% | $+447.48 | $-343.98 | 1.37 | +2.24 | $-3720 |

