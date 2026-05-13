# Microprice continuation overlay — exploratory (THROWAWAY)

Branch: `analysis/microprice-continuation-exploratory-throwaway` (throwaway / archive only; never merges to main).
Generated: 2026-05-13T10:17:52

## 1. Disclosure

## DISCLOSURE — in-sample exploratory, cannot validate

This is exploratory in-sample analysis. The microprice continuation
parameters (Stoikov formula, 2-tick threshold, 60-second persistence)
were chosen from first principles before seeing this data, but the test
runs on the same 160-session corpus used for:
- TRCB-v1 Phase 2 and post-mortem (Q1-Q4)
- TRCB-v2 Phase 2/3 and Q6-Q8
- Cell-breakdown analysis
- Q9 GEX mechanism diagnostic
- GEX permutation re-run
- All-bugfix baseline

The corpus is thoroughly consumed. Even with first-principles parameters,
results here cannot serve as validation. They serve only to filter:
- If microprice adds substantial Sharpe lift (>0.5): worth pre-registering
  for fresh-data forward test
- If microprice adds nothing or hurts: drop the concept
- If marginal: defer decision

No deployment authorization. No strategy modification. No baseline change.


## 2. Locked methodology (no tuning)

- **Microprice (Stoikov)**: `(bid_sz·ask_px + ask_sz·bid_px) / (bid_sz + ask_sz)`
- **Adverse threshold**: 2 ticks (0.50 ES points) against the trade direction
- **Persistence**: 60 consecutive seconds of adverse condition required
- **Exit fill**: best bid − 0.5 tick (long) / best ask + 0.5 tick (short) at the firing second; same per-side slippage as existing time-stop exits
- **Trade pool**: bugfixed IS (257) + bugfixed OOS (247) = 504 trades
- All other OMEN exits unchanged. Microprice fires only if no other exit hit first.

## 3. Implementation diagnostics

- Trades total: **504**
- Microprice-evaluable: **486** (96.4%) — has book ticks and window ≥ 60s
- Microprice fired: **361** (71.6% of all trades; 74.3% of evaluable trades)

⚠ **Fire rate > 50%** on evaluable trades. Microprice is acting as a generic exit trigger, not a continuation-confirmation. Likely fitting to noise.

## 4. Three-arm comparison (per sample)

### IS (74 sessions, 257 trades)

| arm | N | win | mean $ | sum $ | Sharpe | max DD |
|---|---:|---:|---:|---:|---:|---:|
| A1 — full OMEN | 257 | 49.4% | $+47.24 | $+12140 | +2.57 | $-3639 |
| A2 — OMEN-minus-SL | 192 | 45.3% | $+27.10 | $+5202 | +1.23 | $-5265 |
| A3 — OMEN-minus-SL + microprice | 192 | 21.4% | $-58.78 | $-11285 | -2.63 | $-15108 |

### OOS (72 sessions, 247 trades)

| arm | N | win | mean $ | sum $ | Sharpe | max DD |
|---|---:|---:|---:|---:|---:|---:|
| A1 — full OMEN | 247 | 45.3% | $+8.28 | $+2046 | +0.51 | $-6719 |
| A2 — OMEN-minus-SL | 179 | 46.9% | $+33.65 | $+6024 | +1.88 | $-3431 |
| A3 — OMEN-minus-SL + microprice | 179 | 22.9% | $-170.82 | $-30576 | -5.88 | $-30636 |

### Sharpe lift from microprice overlay (A3 − A2)

- IS Sharpe lift: **-3.87** (+1.23 → -2.63)
- OOS Sharpe lift: **-7.76** (+1.88 → -5.88)

## 5. Microprice-fire diagnostics

Of the 361 trades where microprice fired:
- Would have been **winners** under original exit: **130** (36.0%)
- Would have been **losers**: **231** (64.0%)
- Mean Δ vs original (microprice − orig): **$-255.33/trade**
- Sum Δ across fired trades: **$-92175**
  - On would-have-been-winners: $-769.76/trade × 130 trades
  - On would-have-been-losers : $+34.17/trade × 231 trades

### When does microprice fire within the trade?

| quantile | minutes into trade |
|---:|---:|
| q10 | 1.0 |
| q25 | 1.4 |
| q50 | 2.7 |
| q75 | 6.0 |
| q90 | 12.3 |

## 6. Exit-reason distribution (minus-SL subset)

| exit_reason | A2 original | A3 with microprice |
|---|---:|---:|
| time | 296 | 85 |
| stop | 63 | 10 |
| target | 12 | 9 |
| microprice | 0 | 267 |
| session_close | 0 | 0 |

## 7. Honest verdict

**Verdict: DROP CONCEPT (too generic)**

Microprice fires on 74.3% of evaluable trades. That's not 'continuation confirmation' — it's a generic exit trigger. The 2-tick / 60-sec spec is too sensitive for this corpus.

### Reading the criteria explicitly

- OOS Sharpe lift > 0.5: **NO** (actual -7.76)
- Fire rate in 10-50% window: **NO** (actual 74.3%)
- Cuts losers > winners: **YES** (231 losers, 130 winners)

## 8. Caveats

- **In-sample on consumed corpus.** Cannot validate the concept regardless of result. The 'first-principles parameters' framing is good methodology but does 
  not undo data contamination from the 9 prior analyses on this corpus.
- **The minus-SL framing** (excluding SHORT_long) is itself a consumed-data 
  hypothesis. Adding microprice on top conjures a two-step strategy where both 
  steps were chosen with knowledge of this data.
- **Slippage model**: 0.5 tick adverse on the microprice exit matches the locked 
  CostModel for time-stop exits. Real intra-bar fills may behave differently.
- **Result is brittle to parameter choice**. The 2-tick / 60-sec spec was 
  pre-stated; running the same overlay with 3-tick / 90-sec would give different 
  numbers. The spec parameters are not a knob to tune — but they are also not a 
  guarantee that the chosen values are the right ones for fresh data.
- **The pre-registered OMEN-minus-SL forward test (commit `9c1c22f`) does NOT 
  include microprice.** Any forward-test pre-reg involving microprice would need 
  to be written separately and run on data not yet consumed.

