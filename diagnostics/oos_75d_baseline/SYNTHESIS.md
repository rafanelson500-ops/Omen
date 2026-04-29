# OMEN OOS 75-Day Validation — Synthesis

**Window:** 2025-09-08 → 2025-12-23 (76 trading sessions)
**Locked config:** flow_burst, z=1.8, stop=2.0xATR, target=4.5xATR,
  feature_lookback=20, atr_window=14, time_stop=25min, blackout_lunch=True, 5min bars
**Pre-registration:** locked 2026-04-29 02:27 ET, before any backtest run
**Synthesis date:** 2026-04-29 morning ET

---

## TL;DR

OMEN's locked baseline does NOT pass pre-registered OOS validation criteria.
Daily-equity Sharpe collapsed from in-sample 4.45 → OOS 0.70 (-84%).
However, the strategy is degraded — not broken. Multiple methodology lenses
give different reads. Honest assessment: real but small edge that was
heavily inflated by in-sample selection bias. Deployable edge probably
Sharpe 1.0-1.5, not 4.45. **Do not deploy capital.** 15-22% probability
of finding a recoverable edge through queued filter testing on FRESH
forward data (not OOS).

---

## Engine integrity — confirmed clean

In-sample replication ran the same wrapper script against the in-sample
window and produced:
- Sharpe 4.66 (vs documented 4.45 — within tolerance)
- 178 trades (vs documented 174)
- $25,291 PnL (vs documented $24,649)
- Max DD -$2,594 (exact match)

The wrapper script and locked config are correct. OOS degradation is real,
not artifact.

---

## Tier 1 — Validation metrics

### Headline numbers
- Trades: 158 (vs in-sample 174, expected ~163 for 76-day window)
- Win rate: 0.487 (vs in-sample 0.489 — essentially identical)
- Profit factor: 1.14 (vs in-sample ~1.80)
- Total PnL: $4,154 (vs in-sample $24,649)
- Max DD: -$4,643 (vs in-sample -$2,594)
- p-value: 0.28 (not significant)

### Sharpe breakdown
| Metric | In-sample | OOS | Pre-reg verdict |
|---|---|---|---|
| Daily-equity Sharpe | 4.45 | 0.70 | FAILED (< 1.0) |
| Per-trade Sharpe (raw) | 0.2193 | 0.0479 | -78% |
| Per-trade annualized | 5.13 | 1.10 | borderline FAILED |
| Bar-level Sharpe (close-to-close) | 4.94 | 1.76 | MODERATE band |
| Bar-level (debiased ~30%) | 3.4 | ~1.23 | borderline MODERATE |

### Statistical confidence
- PSR vs zero: 72.68% — MODERATE band (< 95% required for STRONG)
- DSR (N=2 trials): 53.33% — AMBIGUOUS (50-70% band)
- DSR sensitivity: collapses to 40%/28%/17%/10% at N=3/5/10/20
- Skewness: +0.28 (right-skewed, favorable)
- Excess kurtosis: +0.71 (trade-level), +127.5 (bar-level — extreme fat tails)

### Verdict against pre-registered criteria
Multiple lenses, different reads:
- Three metrics (daily Sharpe, per-trade, profit factor) → FAILED band
- Three metrics (PSR, DSR, bar-level Sharpe) → MODERATE/AMBIGUOUS band

**Pre-reg locked decision:** AMBIGUOUS / borderline FAILED

---

## Tier 2 — Stratification (in-sample patterns vs OOS)

### Day-of-week (0DTE thesis)
| Day | 0DTE? | IS PnL | OOS PnL | Verdict |
|---|---|---|---|---|
| Monday | ✓ | $1,074 | $1,056 | Held (was always weak) |
| Tuesday | — | $1,571 | $1,783 | Slightly improved |
| Wednesday | ✓ | **$9,792** | **-$5,450** | **INVERTED** (best → worst) |
| Thursday | — | $3,924 | $4,830 | Improved |
| Friday | ✓ | $8,287 | $1,935 | Severely degraded |

**0DTE concentration:**
- In-sample: Mon/Wed/Fri = 78% of PnL
- OOS: Mon/Wed/Fri = -59% of PnL (net negative)
- Tue/Thu carries OOS PnL (159% — meaning rest is negative)

**Verdict:** 0DTE thesis INVERTED. Sample-specific in-sample finding.

### VIX bucket
| Bucket | IS PnL | IS Sharpe | OOS PnL | OOS Sharpe |
|---|---|---|---|---|
| <15 | $195 | 0.025 | -$850 | -0.362 |
| 15-18 | $2,131 | 0.077 | $4,859 | +0.096 |
| 18-20 | $486 | 0.034 | $2,340 | +0.237 |
| **20-25** | **$18,006** | **0.574** | **-$2,465** | **-0.147** |
| ≥25 | $3,830 | 0.158 | $270 | +0.051 |

**Confound check:** VIX 20-25 split by 0DTE day on OOS:
- 0DTE × VIX 20-25: -$2,631 (n=15)
- non-0DTE × VIX 20-25: +$166 (n=8)
Both subsets negative or flat. Not a 0DTE proxy — bucket itself is dead.

**Verdict:** VIX 20-25 thesis INVERTED. Was 73% of in-sample PnL,
now net negative on OOS.

### Time-of-day
| Bucket | IS Sharpe | OOS Sharpe | Verdict |
|---|---|---|---|
| opening_drive (9:30-9:59) | 0.091 | 0.088 | HELD (nearly identical) |
| afternoon_1 (12:30-13:59) | 0.521 | 0.135 | Degraded but positive |
| afternoon_2 (14:00-15:29) | 0.232 | 0.014 | Severely degraded |
| closing_drive (15:30-16:00) | 0.630 (n=5) | 0.337 (n=7) | Low confidence both |

**Verdict:** Patterns held in direction, magnitudes degraded.
First non-inverting in-sample finding.

### Side × Gamma regime (NEW finding from OOS)
| Cell | n | PnL | Sharpe |
|---|---|---|---|
| LONG × long-gamma | 33 | +$2,460 | +0.197 |
| LONG × short-gamma | 29 | +$3,724 | +0.205 |
| **SHORT × long-gamma** | **48** | **-$4,165** | **-0.151** |
| SHORT × short-gamma | 48 | +$2,135 | +0.078 |

**Marginals:**
- LONG side (all regimes): +$6,184 / Sharpe +0.197
- SHORT side (all regimes): -$2,030 / Sharpe -0.037
- Long-gamma regime: -$1,705 / Sharpe -0.041
- Short-gamma regime: +$5,859 / Sharpe +0.129

**Verdict:** Three of four cells are positive. Single broken cell
(shorts in long-gamma) drags total. Mechanism plausible: in long-gamma
regime dealers buy dips and sell rips — short trades fight that mean
reversion.

### Day-of-week skew note
Short trades fired more often on OOS (96 short vs 62 long) than on
in-sample. Long-side performed better than short-side on OOS, opposite
of in-sample.

---

## Cumulative observations

1. **Two consecutive in-sample sub-patterns inverted on OOS** (0DTE,
   VIX 20-25). These were the two strongest theoretically-grounded
   findings. Their inversion suggests the in-sample 80-day window
   had specific characteristics that don't extend to Sept-Dec 2025.

2. **Time-of-day patterns degraded but didn't invert.** Opening drive
   in particular was almost identical (Sharpe 0.091 → 0.088). This is
   the only finding with stability across windows.

3. **Long trades robust on OOS, short trades broken in long-gamma.**
   The cleanest hypothesis from today's analysis is "shorts in
   long-gamma regime are the broken slice." Theoretically grounded
   (dealer mean reversion in long-gamma), and the broken cell alone
   accounts for most of the OOS underperformance.

4. **Bar-level Sharpe (1.76) higher than daily-equity Sharpe (0.70)
   would suggest** — bar-level is more stable than daily P&L because
   a few bad days (e.g., -$5,450 Wednesdays) drag daily-equity but
   don't fully drag bar-level.

5. **Extreme bar-level kurtosis (+127.5).** Massive fat-tail risk in
   bar returns. The strategy's bar-level distribution has scary
   outlier behavior that bar-level Sharpe doesn't penalize.

---

## What this means

### What's still alive
- Long-only OMEN on OOS would have produced +$6,184 across 76 days
  (Sharpe +0.197). Still not deployable, but positive.
- Removing shorts-in-long-gamma cell improves OOS to ~$8,319 across
  110 trades. Still inadequate, but better.
- Time-of-day patterns have some stability across windows.

### What's dead
- The 0DTE day-of-week thesis (was the highest-conviction finding)
- The VIX 20-25 bucket thesis (was 73% of in-sample PnL)
- The "Sharpe 4.45 deployable edge" headline
- The 88% in-sample DSR — clearly was selection bias

### What we don't know yet
- Whether the long-only or shorts-in-long-gamma kill hypotheses hold
  on FRESH forward data (we'd be curve-fitting if we tested on OOS)
- Whether the bar-level Sharpe of 1.76 is real signal or methodology
  artifact (debiased ~1.23 is closer to honest)
- Whether queued filters (zcharm-as-gate, RVOL, vanna) survive forward

### What's NOT permitted next
- Deploy capital
- Modify locked config
- Test queued filters on the OOS window (curve-fit on OOS)
- Cherry-pick favorable subsets ("just trade Tue/Thu and longs only!")
- Run more variants on OOS hoping for better numbers

---

## Updated probability of finding deployable edge

Pre-OOS (last night): not estimated, baseline assumed strong
Yesterday (after OOS Sharpe 0.70): 15-25%
After 0DTE inversion: 10-18%
After VIX inversion: 5-12%
After side×regime + Tier 1: 12-20%
**After full Tier 1 + Tier 2 synthesis: 15-22%**

Reasoning for the small upward shift: the bar-level Sharpe of 1.76
plus PSR of 73% suggest the strategy has some signal that daily-equity
math underestimated. But it's a small adjustment. Most likely outcome
remains "OMEN doesn't recover to deployable edge."

---

## What comes next

### Immediate (this week)
1. Commit this synthesis + supporting analyses to `analysis/oos-75d-validation` branch
2. Send summary to Zach so he can run his fork's OOS test independently
3. Stop touching the 76-day OOS data — it's burned for filter testing

### When Zach's alignment fix lands (forward test starts)
1. Live forward sessions accumulate on locked config
2. After 30+ sessions: recompute Tier 1 metrics on forward data
3. After 30+ sessions: compute Tier 2 stratification on forward data
4. Compare forward results to both in-sample AND OOS as triangulation

### Filter testing (only on FRESH forward sessions, not OOS)
- zcharm-as-gate (Tier 4.1 from queue)
- Volume / RVOL filter (Tier 4.2)
- Test ONE filter at a time with pre-registered criteria

### Engineering projects (deferred to weekends)
- Walk-Forward MCPT on OOS (Tier 1.3) — only Tier 1 not run today
- IS MCPT with co-permutation (Tier 5.1)
- GEX permutation test (Tier 5.3)

---

**End of synthesis.**
