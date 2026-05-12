# TRCB-v1 Post-Mortem — Synthesis

**Branch:** `analysis/trcb-v1-postmortem-throwaway` (archive only, never merges)
**TRCB-v1 verdict:** FAIL — locked in commit `7748c71` on `diagnostics/mbp10-trcb-filter-v1`
**Purpose of this synthesis:** understand WHY the sensor returned nothing — whether the mechanism is dead at OMEN's timeframe or whether the specific operationalization missed a real effect.

This document does NOT authorize new filter runs on the 160-session corpus. Findings inform future projects on fresh data.

---

## 1. The question

Phase 2 found only 27 triggered bars across 11,992 evaluable bars (0.225%), with mean signed 25-min forward return of −0.96 ES points (t = −0.42). Did the filter fail because:

1. **MECHANISM DEAD** — order-flow microstructure has no predictive power at the resolution/horizon we tested, full stop
2. **SENSOR MISCALIBRATED** — a real effect exists but TRCB-v1's specific (window length / threshold / horizon) operationalization missed it
3. **INCONCLUSIVE** — small sample / extreme rarity makes the question unanswerable from this dataset

---

## 2. Q1 — Delta ratio distribution

**Finding:** The locked P3 threshold of 2.0:1 sits at the **99.52nd percentile** of dominant-side ratio across 12,254 evaluable bars. The median is 1.15; the 95th pct is 1.54; the 99th pct is 1.82. **The threshold was set above the 99th percentile by construction** — i.e. the rarity is in P3 alone, not in P3 ∩ P2 ∩ P4.

Pre-reg rationale (P3 = 2.0:1 over 60s window) was calibrated against V4.1's single-tick 3.0:1 ratio. Over a 60s aggregation window, 2.0:1 corresponds to a much rarer event than the pre-reg drafting assumed: in this corpus, only ~0.5% of bars cleared it on the dominant side, and the per-direction rate (~0.27%) explains the bottleneck observed in Phase 2.

Detail: [`q1_ratio_distribution.md`](q1_ratio_distribution.md)

---

## 3. Q2 — Window length sensitivity

**Finding:** At fixed P2/P3/P4 thresholds and 25-min forward horizon, the **30s window shows mean +1.58 ES points with t = +2.32 (n = 71)** — meaningfully different from the locked 60s window (mean −0.96, t = −0.42, n = 27). 120s and 300s windows trigger 7 and 1 bars respectively, too sparse to evaluate.

| window | n_long | n_short | n_trig | trig_rate | mean fwd (25m) | t vs 0 | sep vs uncond | % > 0 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 30s | 38 | 33 | **71** | 0.5922% | **+1.5775** | **+2.3151** | +1.5257 | 63.4% |
| 60s (locked) | 15 | 12 | 27 | 0.2252% | −0.9630 | −0.4150 | −1.0126 | 55.6% |
| 120s | 6 | 1 | 7 | 0.0584% | +0.1786 | +0.0643 | +0.1264 | 57.1% |
| 300s | 1 | 0 | 1 | 0.0083% | — | — | — | 100% |

**Sanity:** 60s window's buy/sell volumes match Phase 2's `per_bar_volumes.parquet` exactly (0 diffs across 12,480 rows) — same code path, same numbers.

Detail: [`q2_window_lengths.md`](q2_window_lengths.md)

---

## 4. Q3 — Forward-return horizon sensitivity

**Finding** (on the locked-60s n=27 triggered set, 5 horizons): the signal is real at sub-5-minute horizons and **reverses or fades by 15 min, the wrong sign by 25 min, increasingly negative through 60 min**.

| horizon (min) | n | mean signed | t vs 0 | % > 0 | uncond mean | sep vs uncond |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 27 | **+2.7778** | **+9.4785** | 100.0% | −0.0177 | +2.7954 |
| 5 | 27 | **+1.6019** | +1.5418 | 59.3% | +0.0005 | +1.6013 |
| 15 | 27 | −0.8704 | −0.4560 | 33.3% | +0.0305 | −0.9009 |
| **25** | 27 | **−0.9630** | −0.4150 | 55.6% | +0.0488 | −1.0117 |
| 60 | 27 | −3.6204 | −0.8116 | 48.1% | +0.1393 | −3.7597 |

**Caveat at 1-min:** the 1-min forward return is bar-close → bar-close+60s, which is **exactly the window P4 thresholds on**. Every triggered bar by definition has signed 60s price move ≥ 0.25 × ATR. So the 100%-positive and mean = +2.78 at 1-min is partially tautological — it confirms P4 passing, not an independent signal. Only the 5-min and later horizons constitute independent evidence.

At 5 min the mean is still positive (+1.60) above unconditional (+0.001), with t = +1.54 (below the conventional |t|≥2 threshold but suggestive). By 15 min the signal has reversed.

Detail: [`q3_forward_horizons.md`](q3_forward_horizons.md)

---

## 5. Verdict

**SENSOR MISCALIBRATED** — but the calibration that would have helped is incompatible with OMEN's strategy structure.

Two miscalibrations stack:

1. **Window length** (Q2): 30s window with the same locked thresholds shows a positive directional signal (t = +2.32 on n = 71, mean +1.58 at 25-min forward) that the 60s window misses. The shorter window catches a real, time-decaying microstructure event. The 60s window aggregates past the peak of the signal and the ratio dilutes.

2. **Forward horizon** (Q3): the signal that exists at 1-5 min decays through 15 min and reverses by 25 min. OMEN's 25-min time stop horizon is past the decay point of this signal.

**Implication:** even if TRCB-v1 had been operationalized with the better 30s window, it would still have struggled at the 25-min forward horizon (Q3 shows the decay is sharp). And tightening the horizon to match the signal (e.g. 1-5 min) is incompatible with OMEN's locked 25-min time stop.

**For OMEN specifically, this is functionally MECHANISM DEAD AT OMEN'S TIMEFRAME.** The microstructure mechanism (post-burst aggression sustaining) is real on short horizons but cannot be harvested through OMEN's 25-min holding period.

### Honest assessment of sample-size limits

Q2's 30s result (n = 71, t = +2.32) is not bulletproof. Single-tailed p ≈ 0.012; two-tailed p ≈ 0.024. With four window choices tested, naive Bonferroni would put two-tailed p at ~0.10. Reasonable evidence of real signal at the short window, but not "definitely real."

Q3's 1-min mean +2.78 is largely tautological (P4 measurement window). The 5-min mean +1.60 (t = +1.54, p ≈ 0.13) is at best suggestive on n=27.

Q1 is descriptive and not subject to sample-size limits — 99.52nd-percentile placement of P3 = 2.0 is a structural fact of the corpus.

The pattern across all three diagnostics is internally consistent (rare threshold + wrong window + wrong horizon, all three pointing the same direction). That consistency is more compelling than any individual statistic.

---

## 6. Implications for OMEN going forward

1. **TRCB-v1 stays dead.** The pre-reg success criteria for the locked operationalization were not met. The locked OMEN config is not modified.

2. **The microstructure thesis is not invalidated** — only TRCB-v1's specific operationalization is. If a future project wants to revisit, the right form is plausibly:
   - Shorter aggregation window (30s or less)
   - Shorter forward horizon (1-5 min)
   - Threshold calibrated to a less extreme percentile of bar-flow asymmetry (e.g. 90-95th percentile, not 99.5th)
   - A holding period compatible with the signal half-life — fundamentally different from OMEN's 25-min time-stop architecture

3. **This is not a partial rehabilitation of TRCB-v1.** The "30s window would have worked better" finding is a post-hoc observation. Re-running with 30s on this corpus is curve-fitting on already-burned data. Per pre-reg Section 11 FAIL action: *"Concept archived in project 'tested and dead' list. May not be re-tested with adjusted thresholds on this data. Requires genuinely new data (forward sessions not in the 160-session corpus) for any revisit."*

4. **OMEN's locked 25-min time stop is a structural choice that constrains which microstructure mechanisms can be filters.** Any future flow-based filter for OMEN must be evaluated against the constraint that signal must survive to ≥25 min. Q3's decay pattern is one piece of evidence that this constraint is harder than was assumed in the TRCB-v1 pre-reg drafting.

---

## 7. Disclaimer

This diagnostic does NOT authorize any new filter test on the 160-session corpus. Findings are for future-project planning only.

Throwaway branch `analysis/trcb-v1-postmortem-throwaway` — archive only, never merges to main.

Pre-reg discipline boundary: any future flow-filter work on OMEN must be done on FRESH forward sessions (not in the 160-session corpus that produced both the original OMEN trade log and this post-mortem). Post-hoc parameter findings here do not constitute permission to re-test on the same data.
