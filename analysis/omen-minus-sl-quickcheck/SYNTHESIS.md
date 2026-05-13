# OMEN-minus-SHORT_long QUICK CHECK on fresh sessions (THROWAWAY)

Branch: `analysis/omen-minus-sl-quickcheck-throwaway` (throwaway / archive only; never merges to main).
Generated: 2026-05-12T20:53:55

## 1. Disclosure

## DISCLOSURE — quick-check, underpowered

This is a quick exploratory read on a small sample of fresh sessions.
The OMEN-minus-SHORT_long hypothesis was generated from observing
consumed-data cell performance (analysis/omen-cell-breakdown-throwaway).
While the fresh sessions themselves were not previously analyzed for
OMEN trade outcomes, the hypothesis being tested IS data-derived.

Sample size: 11-12 sessions, ~16-24 OMEN-minus-SL trades expected.
This is statistically underpowered. Results inform planning, not validation.
A proper forward-test pre-registration will be written separately and
applied to 30+ accumulated fresh sessions for verdict.


## 2. Sessions analyzed

- Fresh sessions: **8** (2026-04-30 → 2026-05-11)
- Dates with trades:
  - 2026-04-30  (2 trades)
  - 2026-05-01  (2 trades)
  - 2026-05-04  (3 trades)
  - 2026-05-05  (3 trades)
  - 2026-05-06  (3 trades)
  - 2026-05-07  (1 trades)
  - 2026-05-08  (2 trades)
  - 2026-05-11  (2 trades)
- Total trades: **18**

**Excluded from the requested 10-session window:**
- 2026-04-29 — `.missing` GEX sentinel; GexBot has no data for this date.
- 2026-05-12 — ES 1s bars not yet pulled for this session.

## 3. Three-bucket Sharpe table

| bucket | sample | N | sessions | full_omen Sharpe | omen_minus_sl Sharpe |
|---|---|---:|---:|---:|---:|
| IS-174 | IS | 174 | 80 | +5.38 | (not previously computed) |
| OOS-158 | OOS | 158 | 76 | +1.13 | +2.79 |
| fresh-18 | fresh | 18 | 8 | +0.30 | +1.84 |

Fresh additional metrics:

| arm | N | win | mean $ | sum $ | Sharpe | max DD |
|---|---:|---:|---:|---:|---:|---:|
| full_omen | 18 | 61.1% | $+4.72 | $+85 | +0.30 | $-1251 |
| omen_minus_sl | 17 | 64.7% | $+29.93 | $+509 | +1.84 | $-1251 |

## 4. Per-cell breakdown (fresh sessions vs prior IS / OOS)

| cell | IS Sharpe (n) | OOS Sharpe (n) | fresh Sharpe (n) | fresh mean $ | fresh sum $ |
|---|---|---|---|---:|---:|
| LONG_long | +1.54 (27) | +2.12 (33) | n/a (n<10, n=2) | $+438.75 | $+878 |
| LONG_short | +5.05 (60) | +2.07 (29) | n/a (n<10, n=6) | $+89.79 | $+539 |
| SHORT_long | +3.23 (32) | -1.95 (48) | n/a (n<10, n=1) | $-423.75 | $-424 |
| SHORT_short | +0.78 (55) | +1.01 (48) | n/a (n<10, n=9) | $-100.83 | $-908 |

**Fresh-session cell counts**: 
LONG_long n=2, LONG_short n=6, SHORT_long n=1, SHORT_short n=9. All four cells are individually below the n=10 threshold required for a Sharpe estimate to be meaningful — per-cell PnL totals reported instead, with Sharpe omitted for individual cells.

## 5. Quick-check verdict

**Verdict: DIRECTIONALLY CONSISTENT**

Inputs to the verdict:
- full_omen fresh Sharpe (n=18): +0.30
- omen_minus_sl fresh Sharpe (n=17): +1.84
- Worst-mean cell on fresh data: **SHORT_long** (mean $-423.75, n=1)
- SHORT_long cell on fresh data: n=1, mean $-423.75, sum $-424. IS the worst cell by mean.

Both criteria met: minus-SL outperforms full on fresh AND SHORT_long is the 
worst cell on fresh data. Direction matches the OOS-158 cell-breakdown 
finding. The sample size is still too small for a statistical claim.

**FRAGILITY NOTE — read this carefully.**
The 'SHORT_long is the worst cell by mean' input rests on **n=1** SHORT_long trade(s) in this window. 
By **total dollars**, SHORT_short (n=9, sum=$-908) is doing *more* damage than SHORT_long (n=1, sum=$-424). 
The Sharpe lift from omen_minus_sl (+0.30 → +1.84) is therefore driven by removing the single biggest losing trade — a coin-flip event at this sample size. Re-run when more sessions accumulate before interpreting the direction as a replication.

## 6. What this means for planning the proper forward test

- Hypothesis remains **worth pre-registering** for a proper forward test.
- Target: ≥ 30 fresh sessions accumulated (≈ 60+ OMEN-minus-SL trades expected).
- Lock 1-arm A/B (`full_omen` vs `omen_minus_sl`) in the pre-reg; report 
  Sharpe + bootstrap CIs.
- Do NOT deploy until that test runs and passes its pre-reg gate.

## 7. Caveats (mandatory)

- **Sample size is far too small for statistical claims.** n=18 trades in 8 sessions. 
  Sharpe estimates at this n are dominated by 1-2 outlier trades.
- **The hypothesis was derived from consumed data.** Even a positive result here 
  is not a clean validation — the cells were named precisely because they 
  performed differently in the OOS-158 sample.
- **Forward-test pre-registration on 30+ accumulated sessions remains required.** 
  This quick-check is a planning input, not a verdict.
- **Do not deploy OMEN-minus-SL based on this result regardless of outcome.** 
  Hard rule, applies whether the verdict is CONSISTENT or INCONSISTENT.
- **Per-cell n is below 10 for every cell** (LONG_long=2, LONG_short=6, 
  SHORT_long=1, SHORT_short=9). 
  Per-cell Sharpes are omitted; per-cell mean/sum are reported but should 
  not be over-read.
- 2026-04-29 excluded due to GexBot `.missing` sentinel. 2026-05-12 excluded 
  due to ES 1s bars not yet pulled. Either could shift the count slightly.
