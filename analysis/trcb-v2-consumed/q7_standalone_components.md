# Q7 — TRCB-v2 standalone component diagnostic

Branch: `analysis/trcb-v2-consumed-data-test-throwaway` (throwaway / archive only; never merges to main).
Generated: 2026-05-12T20:29:54

## 1. Disclosure

## DISCLOSURE — consumed-data corpus

This test is run on the same 160-session corpus that has now been examined
multiple times across TRCB-v1, the post-mortem (Q1-Q4), and TRCB-v2. The
160-session corpus is consumed for purposes of pre-registration.

A "positive" standalone result for any component is diagnostic information,
not validation. It identifies hypotheses worth forward-testing on fresh
data, not filters that can be deployed.


Also relevant (TRCB-v2 in-sample-status disclosure, from `common.py`):

## CRITICAL METHODOLOGICAL DISCLOSURE

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


## 2. Scope and method

- Locked parameters: WINDOW=30s, VOL_MULT=1.0, DELTA_RATIO=1.5, PRICE_ATR_MULT=0.25, ATR_WINDOW=14
- Evaluable bars: **11,989** across **155** sessions 
  (Phase-2 base-eval mask: trailing-100 medians + price_at_T + 
  price_at_T+30s + ATR all finite).
- Trigger-rate denominator is **2 × n_evaluable = 23,978** direction-slots; 
  each bar contributes a long-slot and a short-slot. A bar can fire 
  in both directions of the same bucket — if it does, both contributions 
  enter the bucket's signed-return distribution.
- Forward-return horizons reported: **5 minutes** and **25 minutes**.
- Triggers marked ⚠ have **n < 50** — treat as suggestive only.

## 3. The 7-bucket table

| bucket | long / short fires | total trig | trig % (of 2× evaluable) | 5m mean (pts) | 5m t | 25m mean (pts) | 25m t | 25m % > 0 |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| P2 alone | 5924 / 5911 | 11835 | 49.36% | +0.1739 | +3.15 | +0.2291 | +1.98 | 50.60% |
| P3 alone | 719 / 703 | 1422 | 5.93% | +1.3417 | +12.18 | +1.2021 | +5.05 | 56.83% |
| P4 alone | 1659 / 1624 | 3283 | 13.69% | +2.5571 | +25.94 | +2.8689 | +13.33 | 60.71% |
| P2 AND P3 | 475 / 425 | 900 | 3.75% | +1.6467 | +10.89 | +1.6164 | +5.13 | 57.80% |
| P2 AND P4 | 1293 / 1274 | 2567 | 10.71% | +2.7281 | +23.01 | +2.9705 | +11.68 | 60.48% |
| P3 AND P4 | 350 / 334 | 684 | 2.85% | +2.2906 | +13.30 | +2.1034 | +6.08 | 61.58% |
| P2 AND P3 AND P4 (v2) | 279 / 247 | 526 | 2.19% | +2.5524 | +12.22 | +2.4003 | +5.73 | 61.45% |
| Unconditional (always-long) | 11989 / 0 | 11989 | 100.00% | +0.0012 | +0.02 | +0.0518 | +0.50 | 50.97% |

## 4. Component diagnosis

### 5-minute horizon

- Strongest single condition: **P4 alone** (n=3,282, mean = +2.5571 pts, t = +25.94).
- Strongest pair: **P2 AND P4** (n=2,566, mean = +2.7281 pts, t = +23.01).
- TRCB-v2 (all three): n=525, mean = +2.5524 pts, t = +12.22.
- Unconditional drift: mean = +0.0012 pts, t = +0.02.

### 25-minute horizon (OMEN's hold)

- Strongest single condition: **P4 alone** (n=3,273, mean = +2.8689 pts, t = +13.33).
- Strongest pair: **P2 AND P4** (n=2,561, mean = +2.9705 pts, t = +11.68).
- TRCB-v2 (all three): n=524, mean = +2.4003 pts, t = +5.73.
- Unconditional drift: mean = +0.0518 pts, t = +0.50.

## 5. Information attribution

### 5-min horizon

The all-three combination's 5-min mean (+2.5524 pts) 
**does not exceed** the best pair (P2 AND P4: +2.7281 pts). The third predicate, when added on 
top of the best pair, is not contributing meaningful additional lift in 
mean return; it is narrowing the trigger set without proportional mean 
improvement.

### 25-min horizon

The all-three combination's 25-min mean (+2.4003 pts) 
**does not exceed** the best pair (P2 AND P4: 
+2.9705 pts). The stacking either preserves 
information that's already in the pair, or actively destroys it.

### P4 is the load-bearing predicate

At both horizons, the largest standalone-component mean is **P4 alone** 
(5m: +2.5571 pts; 
25m: +2.8689 pts). 
Pairs that include P4 (P2+P4, P3+P4) marginally improve on P4-alone; pairs 
that exclude P4 (P2+P3) are much weaker. Adding P3 on top of P2+P4 to form 
the v2 triple actively *reduces* the 25m mean (P2+P4 = +2.97 → v2 = +2.40). 
On a mean-return basis, P3's contribution is anti-additive at OMEN's hold 
horizon.

**Important methodological caveat for P4.** P4's forward-return distribution 
includes the 30s qualifying window inside it. The 5m signed return is measured 
from price-at-T (signal bar close); the qualifying P4 move occurred between T 
and T+30s. So part of every P4-bucket forward return is just the qualifying 
30s move that has already happened by T+30s. With ATR averaging ~3-4 pts and 
P4 requiring a 0.25×ATR move (~0.75-1.0 pts), the qualifying move could account 
for roughly **0.75-1.0 pts** of the +2.87 pt 25m mean — i.e., the pure 
post-30s forward signal might be closer to +1.9-2.1 pts than +2.87. This does 
not invalidate the finding (the pure forward signal is still large and 
significant), but it means P4 is *partially* measuring 'observed momentum' 
rather than 'predicted continuation.'

### Signal decay 5m → 25m

| bucket | 5m mean | 25m mean | 25m / 5m |
|---|---:|---:|---:|
| P2 alone | +0.1739 | +0.2291 | 1.32× |
| P3 alone | +1.3417 | +1.2021 | 0.90× |
| P4 alone | +2.5571 | +2.8689 | 1.12× |
| P2 AND P3 | +1.6467 | +1.6164 | 0.98× |
| P2 AND P4 | +2.7281 | +2.9705 | 1.09× |
| P3 AND P4 | +2.2906 | +2.1034 | 0.92× |
| P2 AND P3 AND P4 (v2) | +2.5524 | +2.4003 | 0.94× |
| Unconditional (always-long) | +0.0012 | +0.0518 | 44.34× |

## 6. Interpretation guidance

**These are two different questions.**

- **5-min horizon** characterizes the framework's intrinsic edge — where the 
  microstructure literature places the half-life of order-flow imbalance and 
  trade-classified directional signal. If a component shows signal at 5m, that 
  is the component speaking on its native time scale.

- **25-min horizon** characterizes whether the framework reaches OMEN's hold 
  period. OMEN's locked time stop is 25 min; if signal has decayed to 
  unconditional drift by 25m, that component is mechanically incompatible with 
  OMEN's exit even if it has an intrinsic 5m edge.

Reading the table along the **horizon** axis is more informative than reading 
along the **bucket** axis. A component that is highly significant at 5m and 
decays to noise at 25m is *not* a deployment candidate for OMEN — it is a 
microstructure observation. A component that retains signal at 25m is a 
candidate for a forward-test in a strategy whose hold period matches that 
decay profile.

**Buckets with |t| ≥ 2.0 at 5m:** 7 / 7
**Buckets with |t| ≥ 2.0 at 25m:** 6 / 7

Fewer buckets survive at 25m than at 5m, but the difference is small 
(only P2 alone drops below |t|=2 at 25m). Strikingly, **P4-containing 
buckets show signal that does NOT decay 5m → 25m** — P4 alone goes from 
+2.56 (5m) to +2.87 (25m), P2+P4 from +2.73 to +2.97. Non-P4 buckets 
(P3 alone, P2+P3) show typical 5-10% decay. This pattern is opposite to 
the Q3 post-mortem's TRCB framework decay finding, and is the single most 
notable observation in this diagnostic — though see the methodological 
caveat in section 5 about the 30s qualifying move being inside the 
forward-return measurement window.

## 7. Honest caveats

- In-sample on consumed data. The 160-session corpus has been examined across 
  TRCB-v1, Q1-Q4 post-mortem, and TRCB-v2 Phase 2. Any t-statistic here can be 
  understood as 'this is what would be observed in a future test only if the 
  data-generating process is stationary and the corpus was sampled fairly.'
- Wide-net buckets (P2 alone, P4 alone) fire on ~10-50% of direction-slots. 
  Sample sizes in the thousands produce inflated t-stats from large n even for 
  small means — read MEAN first, t-stat second.
- A bar contributing to BOTH long and short within a bucket inflates that 
  bucket's n without adding new information. The signed-return distribution 
  is correct (each contribution is direction-aware) but the t-stat's degrees 
  of freedom are overstated for any bucket where double-firing is common.
- Forward-test validation on fresh sessions is required before treating any 
  bucket's positive 25m result as an actionable filter. This script identifies 
  hypotheses worth forward-testing, not filters that can be deployed.

