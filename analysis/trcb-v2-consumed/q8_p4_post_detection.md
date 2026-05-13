# Q8 — P4 post-detection diagnostic

Branch: `analysis/trcb-v2-consumed-data-test-throwaway` (throwaway / archive only).
Generated: 2026-05-12T20:40:49

## 1. Disclosure

## DISCLOSURE — consumed-data corpus

This test is run on the same 160-session corpus that has been examined
multiple times across TRCB-v1, the post-mortem (Q1-Q4), TRCB-v2 Phase 2/3,
and Q6/Q7 component diagnostics. The corpus is consumed.

P4 alone showed strong-looking 25-min forward returns in Q7, but that
measurement included the qualifying 30-second move within the forward
return. This test isolates the post-detection signal.


## 2. Setup

- Locked params: WINDOW=30s, PRICE_ATR_MULT=0.25, ATR=14
- Evaluable bars: 11,989
- P4 total fires (long + short): **3,283**
- Reference points: T = signal bar close. T+30s = the moment P4 
  detection becomes available. All Q8 forward returns and MFE/MAE are 
  measured from T+30s (not T) — stripping the qualifying 30s move 
  out of the measurement.
- Unconditional baseline: 1000 random evaluable bars with 
  direction randomized 50/50 (so the baseline is direction-balanced like 
  the P4 sample).
- RTH-truncated P4 fires (T+30s+25min would cross 16:00 ET): 348

## 3. Tables

### Table A — Post-detection forward returns (from T+30s)

Signed by P4-fire direction (long-fires use +1, short-fires use −1). 
Unconditional row uses randomized direction.

| horizon (post-T+30s) | P4 n | P4 mean (pts) | P4 t | P4 % > 0 | uncond n | uncond mean | uncond t |
|---|---:|---:|---:|---:|---:|---:|---:|
| +1 min | 3,215 | -0.0714 | -1.43 | 45.79% | 987 | +0.1114 | +1.44 |
| +5 min | 3,151 | -0.2740 | -2.58 | 47.67% | 969 | -0.0041 | -0.02 |
| +15 min | 3,014 | +0.0015 | +0.01 | 49.90% | 946 | +0.0566 | +0.19 |
| +25 min | 2,929 | +0.0590 | +0.25 | 49.44% | 916 | +0.2677 | +0.66 |

### Table B — Qualifying move (already-completed portion, signed by direction)

This is the move INSIDE the qualifying 30s that defined the P4 trigger. 
It is part of Q7's forward-return measurement but is excluded from Q8's.

| sample | n | mean (pts) | q25 | q50 | q75 | min | max |
|---|---:|---:|---:|---:|---:|---:|---:|
| All P4-fires | 3,283 | +2.8286 | +1.5000 | +2.5000 | +3.5000 | +0.5000 | +24.7500 |
| Long fires | 1,659 | +2.8807 | +1.7500 | +2.5000 | +3.5000 | +0.5000 | +17.7500 |
| Short fires | 1,624 | +2.7754 | +1.5000 | +2.2500 | +3.5000 | +0.5000 | +24.7500 |

### Tables C, D, F — MFE/MAE on P4-fires (vs unconditional)

All measured from T+30s over a 25-minute post-detection window. 
Direction-signed (long fires use +1, short fires use −1; unconditional 
uses random 50/50 direction).

| sample | n | MFE mean | MFE median | MAE mean | MAE median | t→MFE mean (s, %win) | final mean | giveback mean | MFE/\|MAE\| median |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| P4 all | 3,216 | +8.533 | +5.750 | -8.544 | -5.750 | 689s (46.0%) | +0.046 | +8.488 | 0.960 |
| P4 long | 1,628 | +8.094 | +5.500 | -8.593 | -5.750 | 703s (46.9%) | +0.163 | +7.931 | 1.000 |
| P4 short | 1,588 | +8.984 | +6.000 | -8.494 | -6.000 | 676s (45.1%) | -0.075 | +9.058 | 0.915 |
| unconditional (random 1k) | 988 | +7.952 | +5.500 | -7.763 | -5.250 | 700s (46.7%) | +0.269 | +7.683 | 1.010 |

### Table E — Path-shape classification (counts and %)

Per Q4 scheme. Applied in order; first match wins. 
`RUN_UP_THEN_FADE`: MFE ≥ 1.0 AND t→MFE < 12.5min AND final < 0.5·MFE. 
`CLEAN_WINNER`: final > 1.0 AND |MAE| < 0.5·final. 
`SLOW_BLEED`: MFE < 1.0 AND final < −1.0. 
`CHOPPY`: MFE > 1.0 AND |MAE| > 1.0 AND |final| < 0.5. 
`OTHER`: anything else.

| sample | RUN_UP_THEN_FADE | CLEAN_WINNER | SLOW_BLEED | CHOPPY | OTHER |
|---|---:|---:|---:|---:|---:|
| P4 all (n=3,216) | 1274 (39.6%) | 753 (23.4%) | 322 (10.0%) | 41 (1.3%) | 826 (25.7%) |
| P4 long (n=1,628) | 602 (37.0%) | 386 (23.7%) | 164 (10.1%) | 25 (1.5%) | 451 (27.7%) |
| P4 short (n=1,588) | 672 (42.3%) | 367 (23.1%) | 158 (9.9%) | 16 (1.0%) | 375 (23.6%) |
| unconditional (n=988) | 389 (39.4%) | 234 (23.7%) | 87 (8.8%) | 17 (1.7%) | 261 (26.4%) |

## 4. Honest comparison to Q7

- **Q7 reported P4-alone 25m mean** (from T): +2.8689 pts.
- **Q8 post-detection 25m mean** (from T+30s): +0.0590 pts.
- **Mean qualifying 30s move**: +2.8286 pts.
- Sanity check: Q8 + qualifying ≈ Q7 → +0.0590 + +2.8286 = +2.8876 (Q7 reported +2.8689).

- **Unconditional 25m baseline** (random direction, random bar): +0.2677 pts.
- **Post-detection edge vs unconditional**: -0.2088 pts.

**Reading**: the qualifying move accounts for a substantial share of Q7's 
apparent 25m edge. Stripping it out reveals the *pure forward* signal — 
which is the relevant quantity for any deployable strategy, because the 
qualifying move has already happened by the time you detect P4.

## 5. MFE/MAE interpretation

- **Average run-up (P4-all MFE mean)**: +8.533 pts in the 
  25-min post-detection window. Median MFE: +5.750 pts.
- **Where does MFE occur?** Mean t→MFE = 689s = 11.5 min (46.0% of window). 
  Median t→MFE = 620s.
- **Giveback** (MFE − final_return): mean = +8.488 pts. 
  Large giveback signals RUN_UP_THEN_FADE pattern dominance.
- **MFE/|MAE| ratio** median: 0.960. Values ≈ 1 mean symmetric paths; > 1 means favorable-tail asymmetry.

### Comparison vs unconditional baseline

| metric | P4 all | unconditional | ratio (P4/unc) |
|---|---:|---:|---:|
| MFE mean (pts) | +8.533 | +7.952 | 1.073× |
| |MAE| mean (pts) | +8.544 | +7.763 | 1.101× |
| final_return mean | +0.046 | +0.269 | 0.170× |
| giveback mean | +8.488 | +7.683 | 1.105× |
| t→MFE mean (s) | +689.492 | +699.904 | 0.985× |

P4-fire bars produce **+0.58 pts of MFE** above what a 
random direction-signed bar produces in a comparable post-T+30s window. 
Random bars also produce MFE — this is the volatility floor — and the 
question is whether P4's MFE is *meaningfully* above that floor.

## 6. Comparison to Q4 (n=27 TRCB-v1 triggers)

Q4 measured MFE/MAE on the 27 TRCB-v1 triggers from a different parameter set 
(60s window, 2.0:1 ratio). Q8 measures it on ~3,200 P4-fires from a single 
predicate of the v2 set — a 100× larger sample.

- **Q4 modal shape**: RUN_UP_THEN_FADE (14/27 = 51.9% of triggers)
- **Q8 modal shape, P4 all**: RUN_UP_THEN_FADE (1274/3216 = 39.6%)
- **Q8 modal shape, unconditional**: RUN_UP_THEN_FADE (389/988 = 39.4%)

If P4-all and unconditional have the **same** modal shape, the path-shape 
pattern is a property of 25-min ES windows generally, not a property of 
P4-fires specifically. If they differ, P4 selects for a different path shape.

Q4's RUN_UP_THEN_FADE was the modal shape, *but the threshold definition is 
specifically tuned to catch 'price moves then fades'* — so seeing it as the 
mode is partly an artifact of the classification rule. Use Q8's same-rule 
comparison on unconditional bars as the calibration.

## 7. Implications

- **Post-detection 25m edge** (-0.21 pts above unconditional) 
  is NEGATIVE. P4 fires actually under-perform random bars on a 25-min 
  forward basis — the qualifying move is followed by reversion in this 
  corpus.

- **MFE on P4-fires** (+8.53 pts) is comparable to 
  unconditional (+7.95 pts). The 'run-up' is just 
  natural volatility — not P4-specific information.

## 8. Caveats

- **In-sample on consumed corpus**: TRCB-v1 Phase 2, Q1-Q4 post-mortem, 
  TRCB-v2 Phase 2/3, Q6, Q7 have all read this 160-session corpus.
- **P4 is partly a momentum indicator**: by construction it fires when price 
  already moved ≥0.25×ATR in 30s. Any MFE pattern may reflect short-horizon 
  momentum autocorrelation that is not stably exploitable.
- **Direction-balanced unconditional baseline**: random direction 50/50 cancels 
  drift but the unconditional MFE/MAE still reflect ES intraday volatility on 
  this corpus. A different period might give different baselines.
- **MFE/giveback is an upper bound, not realizable PnL**: 'mean MFE' requires 
  perfect exit timing. A real exit rule (target/stop/time) will capture only a 
  fraction of MFE on the winners.
- **Forward-test on fresh sessions required** before any conclusion about 
  whether P4 is a real or curve-fit edge. This corpus is consumed.

