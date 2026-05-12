# TRCB-v2 Phase 2 — Population Validation (IN-SAMPLE, THROWAWAY)

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


**Generated:** 2026-05-12T18:08:40
**Branch:** `analysis/trcb-v2-consumed-data-test-throwaway`

## Locked parameters (v2)

- WINDOW_SECONDS = 30
- VOLUME_MULT    = 1.0
- DELTA_RATIO    = 1.5
- PRICE_ATR_MULT = 0.25
- ATR_WINDOW     = 14 (Wilder RMA on 5-min bars)

## Corpus
- Total RTH 5-min bars: **12,480**
- Fully evaluable bars: **11,989**
- Sessions: **160**
- Date range: 2025-09-08 → 2026-04-28

## Trigger counts
- Triggered LONG: **279**
- Triggered SHORT: **247**
- Total: **526**
- Trigger rate of evaluable: **4.3874%**

## Per-predicate pass counts (evaluable bars)
| direction | P2 | P3 | P4 | all-three |
|---|---:|---:|---:|---:|
| long | 5,924 | 719 | 1,659 | 279 |
| short | 5,911 | 703 | 1,624 | 247 |

## Forward-return signal by horizon
| horizon | n (triggered) | mean signed | std | t vs 0 | %>0 | Welch t vs all-eval-raw | Welch p |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1 min | 524 | +2.6589 | 2.3575 | +25.8169 | 96.37% | +25.3456 | 0.000000 |
| 5 min | 525 | +2.5524 | 4.7872 | +12.2165 | 75.62% | +11.9159 | 0.000000 |
| 15 min | 525 | +2.6957 | 8.0908 | +7.6342 | 65.90% | +7.3555 | 0.000000 |
| 25 min | 524 | +2.4003 | 9.5922 | +5.7281 | 61.45% | +5.4428 | 0.000000 |

## Per-direction signal (signed return at each horizon)
| horizon | long n | long mean | long t | short n | short mean | short t |
|---|---:|---:|---:|---:|---:|---:|
| 1 min | 278 | +2.6601 | +22.6194 | 246 | +2.6575 | +15.2020 |
| 5 min | 279 | +2.7455 | +11.3017 | 246 | +2.3333 | +6.6550 |
| 15 min | 279 | +2.7437 | +6.1289 | 246 | +2.6413 | +4.7347 |
| 25 min | 278 | +2.5522 | +4.5089 | 246 | +2.2287 | +3.5740 |

## Trigger rate by hour (ET, evaluable bars)
| hour | evaluable | triggers | rate |
|---|---:|---:|---:|
| 09:00–09:59 | 770 | 30 | 3.896% |
| 10:00–10:59 | 1,848 | 79 | 4.275% |
| 11:00–11:59 | 1,853 | 72 | 3.886% |
| 12:00–12:59 | 1,859 | 74 | 3.981% |
| 13:00–13:59 | 1,839 | 88 | 4.785% |
| 14:00–14:59 | 1,832 | 92 | 5.022% |
| 15:00–15:59 | 1,835 | 91 | 4.959% |

## Reference: TRCB-v1 Phase 2 (same corpus, different parameters)

```
  v1 (60s window, 2.0:1 ratio): n_trig=27  (long=15, short=12)
  v1 triggered signed 25m return: mean=-0.9630  t=-0.4150  %>0=55.56%
```

## In-sample-status reminder

These numbers describe how the 30s/1.5:1 parameter set behaves on the 
160-session corpus that the post-mortem already informed. They do not 
constitute validation. See the CRITICAL DISCLOSURE at the top of this file.
