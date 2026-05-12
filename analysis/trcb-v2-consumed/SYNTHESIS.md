# TRCB-v2 SYNTHESIS — Consumed-Data Test (IN-SAMPLE, THROWAWAY)

**Generated:** 2026-05-12T18:13:13
**Branch:** `analysis/trcb-v2-consumed-data-test-throwaway` 
(throwaway / archive only; never merges to main)

## 1. Critical Disclosure

This test is NOT a valid pre-registration. The user is running TRCB-v2
on the same 160-session corpus that:
  - TRCB-v1 Phase 2 already consumed
  - Q1/Q2/Q3 post-mortem already analyzed at multiple window lengths
  - Q4 MFE/MAE analysis already consumed
  - Q2 specifically tested the 30s window and showed positive signal

The TRCB-v2 parameters (30s window, 1.5:1 ratio) were chosen AFTER
observing post-mortem results that showed 30s windows produce positive
forward signal. This means the parameter selection was informed by the
data being tested. This is in-sample parameter tuning by definition,
regardless of any pre-registration documentation.

A positive result here does NOT constitute validation of TRCB-v2. It
constitutes evidence that the parameters that already looked good on
this data continue to look good on this data. To validate TRCB-v2, fresh
forward-only sessions must be used in a future test.

A negative result here would be more informative than a positive one —
it would indicate the framework is weaker than the post-mortem suggested.

The user has explicitly overridden methodological objections and is
proceeding with this test knowing the above.

## 2. Phase 2 — population numbers vs TRCB-v1 reference

Both v1 and v2 evaluated on the identical 160-session corpus (2025-09-08 → 2026-04-27).

### Parameters compared
| param | TRCB-v1 (pre-reg b75e995) | TRCB-v2 (in-sample) |
|---|---|---|
| WINDOW_SECONDS | 60 | **30** |
| VOLUME_MULT | 1.0 | 1.0 |
| DELTA_RATIO  | 2.0 | **1.5** |
| PRICE_ATR_MULT | 0.25 | 0.25 |

### Trigger counts
| version | long | short | total | rate of evaluable |
|---|---:|---:|---:|---:|
| TRCB-v1 | 15 | 12 | 27 | 0.2252% |
| TRCB-v2 | 279 | 247 | 526 | 4.3874% |

### Forward-return signal — v2 (this analysis)
| horizon | n | mean signed | t vs 0 | %>0 |
|---|---:|---:|---:|---:|
| 1 min | 524 | +2.6589 | +25.8169 | 96.37% |
| 5 min | 525 | +2.5524 | +12.2165 | 75.62% |
| 15 min | 525 | +2.6957 | +7.6342 | 65.90% |
| 25 min | 524 | +2.4003 | +5.7281 | 61.45% |

### Forward-return signal — v1 (reference, 25-min only)
- n = 27  mean = **-0.9630** pts  t = **-0.4150**  %>0 = **55.56%**

### Per-direction signal at each horizon — v2
| horizon | long n | long mean | long t | short n | short mean | short t |
|---|---:|---:|---:|---:|---:|---:|
| 1 min | 278 | +2.6601 | +22.6194 | 246 | +2.6575 | +15.2020 |
| 5 min | 279 | +2.7455 | +11.3017 | 246 | +2.3333 | +6.6550 |
| 15 min | 279 | +2.7437 | +6.1289 | 246 | +2.6413 | +4.7347 |
| 25 min | 278 | +2.5522 | +4.5089 | 246 | +2.2287 | +3.5740 |

## 3. Phase 3 — filter performance on OMEN trade log (BOTH ARMS)

Per spec: report v2 filter on (full OMEN) AND (OMEN-minus-SL, i.e. trades excluding `SHORT_long` cell). Subsets: all / confirmed / rejected.

| arm | sample | subset | N | win | mean $ | sum $ | Sharpe | max DD |
|---|---|---|---:|---:|---:|---:|---:|---:|
| full_omen | IS | all | 174 | 48.9% | $+141.66 | $+24649 | +5.38 | $-2594 |
| full_omen | IS | confirmed | 6 | 50.0% | $+239.79 | $+1439 | +1.98 | $-392 |
| full_omen | IS | rejected | 168 | 48.8% | $+138.15 | $+23210 | +5.12 | $-2594 |
| full_omen | OOS | all | 158 | 48.7% | $+26.29 | $+4154 | +1.13 | $-4642 |
| full_omen | OOS | confirmed | 1 | 100.0% | $+7.50 | $+8 | — | $+0 |
| full_omen | OOS | rejected | 157 | 48.4% | $+26.41 | $+4146 | +1.12 | $-4642 |
| full_omen | Combined | all | 332 | 48.8% | $+86.75 | $+28802 | +3.45 | $-4642 |
| full_omen | Combined | confirmed | 7 | 57.1% | $+206.61 | $+1446 | +1.41 | $-392 |
| full_omen | Combined | rejected | 325 | 48.6% | $+84.17 | $+27356 | +3.30 | $-4642 |
| omen_minus_sl | IS | all | 131 | 49.6% | $+135.89 | $+17801 | +4.49 | $-2996 |
| omen_minus_sl | IS | confirmed | 6 | 50.0% | $+239.79 | $+1439 | +2.03 | $-392 |
| omen_minus_sl | IS | rejected | 125 | 49.6% | $+130.90 | $+16362 | +4.18 | $-2996 |
| omen_minus_sl | OOS | all | 110 | 52.7% | $+75.62 | $+8319 | +3.03 | $-2704 |
| omen_minus_sl | OOS | confirmed | 1 | 100.0% | $+7.50 | $+8 | — | $+0 |
| omen_minus_sl | OOS | rejected | 109 | 52.3% | $+76.25 | $+8311 | +3.02 | $-2704 |
| omen_minus_sl | Combined | all | 241 | 51.0% | $+108.38 | $+26120 | +3.87 | $-2996 |
| omen_minus_sl | Combined | confirmed | 7 | 57.1% | $+206.61 | $+1446 | +1.49 | $-392 |
| omen_minus_sl | Combined | rejected | 234 | 50.9% | $+105.44 | $+24674 | +3.69 | $-2996 |

## 4. Honest interpretation

**These results were generated on data the parameters were chosen from. 
Positive findings here are consistent with selection bias and do not 
constitute validation.**

**Any deployment decision based on these results would be acting on 
consumed-data findings without forward-test validation.**

**The post-mortem already established that TRCB framework signals decay 
by minute 15. Phase 3 results showing OMEN improvement on 25-min hold 
should be viewed with skepticism given the mechanism conflict.**

### What the numbers actually show

**Phase 2 (population) shows a strong-looking signal at every horizon:**
- 1-min: n=524, mean=+2.66 pts, t=+25.82, %>0=96.4%
- 5-min: n=525, mean=+2.55 pts, t=+12.22, %>0=75.6%
- 15-min: n=525, mean=+2.70 pts, t=+7.63, %>0=65.9%
- 25-min: n=524, mean=+2.40 pts, t=+5.73, %>0=61.5%

This separation is exactly what one would expect from in-sample tuning. 
Selecting parameters that maximised forward signal in the post-mortem and 
then measuring forward signal at those parameters on the same data is 
a tautology, not a validation.

**Phase 3 (OMEN trade log) shows a much weaker filter effect:**
- v2 fires on **7 / 332** trades total (IS: 6 / 174, OOS: 1 / 158).
- full_omen IS: confirmed Sharpe = **+1.98** vs all-IS Sharpe = **+5.38**. Confirmed is *worse* on a Sharpe basis despite higher mean per-trade $.
- full_omen OOS: only 1 confirmed trade (n=1 → Sharpe undefined). No useful signal from the filter at OOS scale.
- omen_minus_sl OOS: all-Sharpe = +3.03, 
  confirmed-Sharpe = undefined (n=1).

**The two arms (full vs minus-SL) tell almost the same filter story** 
because the SL exclusion happens BEFORE the filter is applied. The 
filter's discriminative power within either arm is statistically 
indistinguishable from random selection at these N's.

**Mechanism conflict the post-mortem already flagged:** the prior Q4 
MFE/MAE analysis on the 27 v1 triggers showed RUN_UP_THEN_FADE as the 
modal shape and median time-to-MFE ≈ 7 min. If v2 inherits the same 
structural property, a 25-min hold systematically gives back favorable 
excursion — meaning a v2-filtered OMEN with the locked 25-min time stop 
would inherit the same mismatched-exit problem.

## 5. What this test cannot answer that a forward test could

**This test can answer:**
- Whether 30s/1.5:1 produces more triggers than 60s/2.0:1 on this corpus → yes.
- Whether triggered bars in this corpus have favorable forward-return mean → yes.
- Whether the v2 filter fires on the OMEN trade log in this corpus → rarely (2.1%).

**This test cannot answer:**
- Whether the apparent edge replicates on data not used to choose parameters.
- Whether the 1.5:1 ratio is the right threshold for 30s windows in general.
- Whether the strong t-stats at 1m/5m horizons reflect a genuine impulse 
  or a quirk of this corpus's price-microstructure regime.
- Whether a forward-only sample would show the same per-direction balance 
  (long mean ≈ short mean) seen here.

### Sample size needed for a forward-only validation

Power calculation rough sketch (informative only — not a pre-reg):
- Population-trigger rate of ~4.4% means ~3.4 triggers per evaluable session.
- The observed v2 25-min mean is +2.40 pts, std 9.59 pts.
- Effect size d ≈ 0.250. 
- For ~80% power at α=0.05 (one-sided) to detect that effect, n ≈ 70-100 
  triggers needed → roughly 20-30 fresh trading sessions if the corpus 
  produces 3.4 triggers per session and the effect size is real.
- For Phase-3-level claims on OMEN trade log, much more: with v2 firing on 
  ~2% of OMEN entries, 30-50 sessions of fresh data would yield only 
  ~3-5 v2-confirmed OMEN trades — insufficient. To test the FILTER on 
  OMEN's actual signal cadence would require **hundreds** of fresh 
  sessions, not a few weeks.

### Recommendation

Treat these Phase 2 / Phase 3 numbers as descriptive of a tuned 
parameter set on consumed data. No deployment action. If TRCB-v2 is 
genuinely a candidate, lock 30s/1.5 today, and only collect forward 
data **with no further parameter changes**. The v2 filter's apparent 
low fire rate on OMEN trades suggests it is unlikely to be useful as 
a confirmation filter for OMEN's signal in its current form.

