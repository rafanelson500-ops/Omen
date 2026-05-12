# Q6 — TRCB-v2 bottleneck diagnosis

Branch: `analysis/trcb-v2-consumed-data-test-throwaway` (throwaway / archive only).
Generated: 2026-05-12T18:22:34

**Scope.** Descriptive diagnosis of why TRCB-v2 confirmed only 7 of 332 OMEN 
trades. No new parameter tests, no new filter spec. Each trade's predicate flags 
are projected to the trade's OWN side (`p2_long` if `side=+1` else `p2_short`, 
etc.); the population is expanded to 'direction-slots' (each evaluable bar 
contributes one long-direction slot and one short-direction slot) for an 
apples-to-apples comparison.

- OMEN trades total: **332**
- FILTER_EVALUABLE (trailing-100 finite AND bar matched in per_bar_volumes_30s): **254** (76.5%)
- FILTER_CONFIRMED: **7 / 332** (2.1%)
- Population direction-slots: **23,978** (each evaluable bar contributes 2)
- Population L2 triggers (all-three pass): **526** 
  (2.1937% of slots)

## 1. Per-condition pass rates (OMEN vs population)

All three predicates evaluated independently (regardless of the other two).
OMEN row = evaluable subset (256 trades). Population row = direction-slots.

| condition | OMEN trades | population | ratio (OMEN/pop) |
|---|---:|---:|---:|
| P2 (volume vs trailing median) | 48.03% | 49.36% | 0.973× |
| P3 (directional / opposite ratio) | 7.09% | 5.93% | 1.195× |
| P4 (price move / 0.25·ATR) | 15.35% | 13.69% | 1.121× |

## 2. Single primary bottleneck

Failure attribution among **247 evaluable-rejected trades** 
(P2/P3/P4 = pass-flag for the trade's OWN direction):

| failure pattern | count | % of rejected |
|---|---:|---:|
| P2 fails alone (P3, P4 pass) | 2 | 0.8% |
| P3 fails alone (P2, P4 pass) | 26 | 10.5% |
| P4 fails alone (P2, P3 pass) | 3 | 1.2% |
| P2 + P3 fail (P4 passes) | 4 | 1.6% |
| P2 + P4 fail (P3 passes) | 6 | 2.4% |
| P3 + P4 fail (P2 passes) | 86 | 34.8% |
| All three fail | 120 | 48.6% |

Per-condition failure involvement (any bucket where Pi fails):

| condition | failures involving | % of rejected |
|---|---:|---:|
| P2 | 132 | 53.4% |
| P3 | 236 | 95.5% |
| P4 | 215 | 87.0% |

## 3. Distribution comparison (OMEN entry bars vs population direction-slots)

Quantiles of the raw inputs to P2/P3/P4, computed on the trade's own direction:

### delta_ratio — P3 input — directional / opposite aggressive ratio (passes if ≥ 1.5)

| quantile | OMEN trades | population |
|---|---:|---:|
| 0.05 | 0.6150 | 0.6213 |
| 0.25 | 0.8298 | 0.8380 |
| 0.50 | 0.9535 | 0.9957 |
| 0.75 | 1.1897 | 1.1816 |
| 0.95 | 1.6006 | 1.5397 |

### vol_vs_median — P2 input — directional volume / trailing-100 median (passes if ≥ 1.0)

| quantile | OMEN trades | population |
|---|---:|---:|
| 0.05 | 0.3745 | 0.3648 |
| 0.25 | 0.7158 | 0.6578 |
| 0.50 | 0.9647 | 0.9887 |
| 0.75 | 1.6067 | 1.5609 |
| 0.95 | 5.0410 | 3.3914 |

### signed_atr_units — P4 input — signed price move / (PRICE_ATR_MULT × ATR) (passes if ≥ 1)

| quantile | OMEN trades | population |
|---|---:|---:|
| 0.05 | -1.8091 | -1.6173 |
| 0.25 | -0.6171 | -0.5975 |
| 0.50 | 0.0000 | 0.0000 |
| 0.75 | 0.6444 | 0.5975 |
| 0.95 | 1.9308 | 1.6173 |

Means (for context):

| metric | OMEN mean | population mean |
|---|---:|---:|
| delta_ratio | 1.0286 | 1.0233 |
| vol_vs_median | 1.5112 | 1.3105 |
| signed_atr_units | -0.0093 | 0.0000 |

## 4. Time-of-day overlap

OMEN trades total: **332**. Population L2 triggers (all-three pass): **526**.

| hour (ET) | OMEN n | OMEN % | pop trig n | pop trig % |
|---|---:|---:|---:|---:|
| 09:00–09:59 | 76 | 22.9% | 30 | 5.7% |
| 10:00–10:59 | 2 | 0.6% | 79 | 15.0% |
| 11:00–11:59 | 0 | 0.0% | 72 | 13.7% |
| 12:00–12:59 | 12 | 3.6% | 74 | 14.1% |
| 13:00–13:59 | 30 | 9.0% | 88 | 16.7% |
| 14:00–14:59 | 105 | 31.6% | 92 | 17.5% |
| 15:00–15:59 | 107 | 32.2% | 91 | 17.3% |

## 5. Interpretation

### The headline answer: there is no OMEN-specific bottleneck

Per-predicate pass rates on evaluable OMEN trades are essentially **identical to 
the random-bar baseline** (population direction-slots):

| condition | OMEN (n=254) | population | OMEN / pop |
|---|---:|---:|---:|
| P2 | 48.0% | 49.4% | 0.97× |
| P3 | 7.1% | 5.9% | 1.19× |
| P4 | 15.4% | 13.7% | 1.12× |

All three pass rate: **OMEN evaluable = 2.76%** 
vs **population = 2.19%**. 
OMEN actually confirms at a *marginally higher* rate than the population baseline. 
**The data does not show OMEN being systematically suppressed by any one predicate.**

### What's actually driving the 7/332 result

Two factors combine:

1. **Filter rarity is by design.** v2's joint-pass rate is ~2-3% on ANY direction-
   slot in this corpus — this is a property of stacking three independent 
   predicates, each passing 6-50% of the time. Even if every OMEN trade were 
   sampled uniformly from the population, ~2.2% would confirm. Observed OMEN 
   confirm rate (2.8%) matches that ceiling within noise.

2. **78 / 332 trades (23.5%) are 
   structurally unevaluable.** These fire at entry_time=09:30:00 ET (RTH open, 
   before the first 5-min bar closes). There is no 5-min bar at 09:30 in the 
   per_bar_volumes table — the rolling-100 trailing median is also undefined 
   there. These trades cannot pass the filter regardless of microstructure.

Of the 254 evaluable trades, 7 
confirmed = 2.8%. Of the 78 unevaluable trades, 
0 confirmed (by construction). Combined: 7 / 332 = 2.1%, vs the per-slot population 
baseline of 2.2%. **OMEN trades and random direction-slots confirm at the same rate.**

### Failure attribution among rejected evaluable trades

Inside the 247 rejected evaluable trades, P3 is involved in 95.5% 
of failures, P4 in 87.0%, P2 in 53.4%. 
**Note**: this ranking just reflects the unconditional rarity of each predicate 
(P2 fires ~50%, P4 ~15%, P3 ~6% across all bars). P3 'wins' the failure tally 
because P3 is the rarest predicate to pass — not because OMEN signal bars are 
anti-aligned with P3. The opposite, in fact: OMEN's *upper-tail* delta_ratio is 
slightly heavier than population (95-pct OMEN = 1.601 vs 1.540), so OMEN's P3 pass 
rate (7.1%) is HIGHER than population's (5.9%).

### Tested hypotheses that the data does NOT support


- **'OMEN signals identify balanced-flow conditions' → NOT SUPPORTED.** 
  OMEN's *median* own-direction delta ratio (0.954) is slightly 
  *below* population (0.996), which would point this way — but 
  what matters for the P3 predicate is the upper tail (above 1.5), and OMEN's 
  upper tail is slightly *heavier* than population's. OMEN bars are if anything 
  more (not less) likely to clear the 1.5:1 threshold.

- **'P3 is the chokepoint that suppresses OMEN trades' → NOT SUPPORTED.** 
  OMEN's P3 pass rate (7.1%) exceeds population's 
  (5.9%). P3 'wins' the failure tally only because it's the 
  rarest predicate overall — it would dominate failures on a random-bar baseline 
  in the same way.

- **'P4 is the chokepoint that catches the pause-after-move' → NOT SUPPORTED.** 
  OMEN's P4 pass rate (15.4%) is comparable to or marginally 
  above population's (13.7%). signed_atr_units distributions 
  are nearly identical at every quantile.

### Time-of-day distributions DO diverge — but it doesn't matter mechanistically

Max hourly-share difference between OMEN trades and population L2 triggers is 
**17.2 percentage points** (e.g., OMEN at 09:00 = 22.9% — mostly the unevaluable 09:30 cluster — vs population 
L2 triggers at 09:00 = 5.7%; OMEN at 14:00 = 31.6% vs population = 17.5%; OMEN at 15:00 = 
32.2% vs population = 17.3%). OMEN is 
afternoon-skewed; population L2 triggers are flat across 10-15.

**But** OMEN's afternoon-skewed hours don't suppress per-predicate pass rates — 
section 1 shows OMEN passes each P2/P3/P4 at population-level rates. The hour 
mismatch doesn't translate to a microstructure mismatch in this corpus.

### Fixability — honest assessment


There is no 'fix' because there is no anomaly to fix. The 7/332 outcome reflects:

- (a) v2's joint pass rate is inherently ~2% regardless of which bar set you sample, and
- (b) ~23% of OMEN trades fire at 09:30 RTH-open, structurally unevaluable by v2's 
  5-min-bar-anchored mechanic.

Parameter changes to v2 (looser thresholds) would raise the joint pass rate on 
BOTH populations equally, producing more confirmed OMEN trades but with worse 
signal-to-noise. They would not produce OMEN-specific lift unless OMEN trades 
had a microstructure signature the filter was missing — and section 1 shows they 
don't.

The earlier write-up's 'mechanism conflict / OMEN selects balanced-flow' framing 
should be retracted on the strength of this diagnostic. The 7/332 number is 
uninformative about edge or anti-correlation; it is consistent with random 
sampling at the joint pass rate of v2.

## 6. Honest caveats

- Descriptive analysis of already-produced data. No new filter spec, no new parameters.
- n=254 evaluable OMEN trades is small. Confidence intervals on the 'OMEN matches 
  population' claim are wide; a fresh-data check could move the per-predicate ratios.
- The 76 trades at entry_time=09:30:00 are excluded from the evaluable subset by 
  construction (no matching 5-min bar; rolling median undefined). Reconciling them 
  would require redefining the v2 evaluation timestamp, not adjusting a threshold.
- Population baseline uses per-direction-slots (each bar counted twice — long and 
  short slots). This matches OMEN's direction-specific signaling but is not the 
  same as the 4.4% all-three rate quoted in the Phase 2 SYNTHESIS, which was over 
  bars regardless of direction.
