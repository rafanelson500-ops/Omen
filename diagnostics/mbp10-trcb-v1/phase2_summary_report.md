# TRCB-v1 Phase 2 — Population-Level Validation Report

**Generated:** 2026-05-12T16:06:03
**Pre-reg commit:** `b75e995`
**Header note:** *Produced under pre-registration commit `b75e995`. Parameters locked (P1=60s, P2=1.0×, P3=2.0:1, P4=0.25×ATR, ATR_WINDOW=14). Not modified based on these results.*

## DST sanity check

- 2025-11-04 (expected EST (-05:00)): first trade on this date → UTC=2025-11-04T19:40:00+00:00, ET=2025-11-04T14:40:00-05:00, offset=-1 day, 19:00:00
- 2026-03-09 (expected EDT (-04:00)): first trade on this date → UTC=2026-03-09T18:35:00+00:00, ET=2026-03-09T14:35:00-04:00, offset=-1 day, 20:00:00

## Corpus
- Total RTH 5-min bars: **12,480**
- Fully evaluable bars (post-100-bar warmup, finite price+ATR): **11,992**
- Sessions covered: 160
- Date range: 2025-09-08 → 2026-04-28

## Trigger counts and rate
- Triggered LONG: **15**
- Triggered SHORT: **12**
- Total triggered: **27**
- Trigger rate over evaluable bars: **0.2252%**

## Per-predicate pass counts (on evaluable bars)
| direction | P2 | P3 | P4 | all-three |
|---|---:|---:|---:|---:|
| long | 5,951 | 32 | 2,338 | 15 |
| short | 5,896 | 26 | 2,431 | 12 |

## 25-min forward return statistics
| sample | n | mean | median | std | t vs 0 | % > 0 |
|---|---:|---:|---:|---:|---:|---:|
| triggered (signed) | 27 | -0.9630 | +1.0000 | 12.0561 | -0.4150 | 55.56% |
| untriggered (raw, no direction) | 11,941 | +0.0437 | +0.2500 | 11.2519 | +0.4241 | 50.93% |
| all evaluable (raw, unconditional) | 11,968 | +0.0496 | +0.2500 | 11.2533 | +0.4821 | 50.96% |

**Welch two-sample t-test triggered (signed) vs all-evaluable (raw):** t = **-0.4360**, p = **0.666436**

## Directional breakdown (triggered, signed)
| direction | n | mean | t vs 0 | % > 0 |
|---|---:|---:|---:|---:|
| triggered LONG | 15 | +1.5333 | +1.0064 | 66.67% |
| triggered SHORT | 12 | -4.0833 | -0.8452 | 41.67% |

## Trigger rate by hour bucket (ET, evaluable bars)
| hour | evaluable | triggers | rate |
|---|---:|---:|---:|
| 09:00–09:59 | 770 | 0 | 0.000% |
| 10:00–10:59 | 1,848 | 4 | 0.216% |
| 11:00–11:59 | 1,854 | 2 | 0.108% |
| 12:00–12:59 | 1,858 | 8 | 0.431% |
| 13:00–13:59 | 1,841 | 5 | 0.272% |
| 14:00–14:59 | 1,833 | 5 | 0.273% |
| 15:00–15:59 | 1,835 | 3 | 0.163% |

## Side-vs-midpoint disagreement (data integrity check)
- Max per-day midpoint-rule-vs-Databento-`side` disagreement rate: **0.0007%**
- Days flagged (>2% threshold): **0**
- Threshold met if zero flagged. The Databento `side` field on trade rows is the **aggressor side** (verified empirically Step 0); the pre-reg midpoint rule on on-row NBBO produces identical classifications across the corpus.

## Verdict (qualitative — per pre-reg Section 6)

- Triggered signed mean = **-0.9630** ES points (n = 27)
- Unconditional raw mean = **+0.0496** ES points (n = 11,968)
- Separation (trig − cond) = **-1.0126**

**READING:** READING: triggered bars mean is non-positive — directional signal missing or wrong sign.
**Looks like FAIL, but pre-reg makes this user's call.**

Pre-reg Section 6 specifies a qualitative gate. The numbers above are presented as the basis for the user's PASS / FAIL / AMBIGUOUS call. Phase 3 does not begin without explicit user confirmation that Phase 2 passed.
