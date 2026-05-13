# OMEN Candidate Mechanism Hypotheses
# Locked: 2026-05-13
# Status: Hypotheses locked WITHOUT testing on consumed data
# Next action: forward-test ONLY after OMEN-minus-SL pre-reg verdict
#              (commit 9c1c22f) produces a result

## Background

After all three bug fixes were applied to OMEN's infrastructure
(features.py session-boundary fix, backtest.py time-stop off-by-one
fix, backtest.py trade overlap fix), the Tier 5.3 GEX permutation
test was re-run on the corrected code.

Results:
  Original Tier 5.3 (buggy code):     p = 0.14
  Bugfixed simple shuffle:            p = 0.27
  Bugfixed block permutation (5d):    p = 0.26

The bug fix moved the p-value UP, not down. Under correct math, OMEN's
performance is statistically indistinguishable from a strategy where
GEX features are randomized. This does not prove the GEX mechanism is
fake — the test is underpowered for small effects — but it does mean
the stated mechanism cannot be defended on current data alone.

This document locks six candidate hypotheses for what OMEN might
actually be catching. They will be forward-tested ONLY after the
OMEN-minus-SL pre-registered forward test produces a verdict.

---

## Hypothesis A — Late-day momentum after liquidity events

### Statement
OMEN's edge is not from GEX-driven dealer hedging. It is from afternoon
trend continuation following morning liquidity events (macro prints,
overnight unwinds, lunch-period re-positioning). The GEX z-score
happens to fire when these post-event resolutions produce directional
moves, but the mechanism is generic trend-after-chop, not dealer flow.

### Reasoning
- OMEN trades concentrate in the afternoon (Zach's 12:30 trading
  window choice was based on the same intuition, even though his
  implementation hurt performance).
- The Q9 finding showed signals are NOT correlated with high-vol
  bars, but morning macro events generate the directional moves
  OMEN catches in the afternoon.
- Cell-breakdown shows SHORT_long broken — this is consistent with
  "afternoon shorts in stabilizing regime fight the recovery from
  morning weakness."

### Operationalization for forward test
- Compute time-of-day distribution of fresh-session OMEN trades
- Check if afternoon-only trades (post-12:30) account for most edge
- Compare to a control: a strategy that trades only afternoons
  using simple 5-min momentum signals, no GEX
- Pre-register this control comparison BEFORE running

---

## Hypothesis B — Volatility regime selection

### Statement
OMEN's ATR-scaled exits drive its edge, not the GEX entry signal.
The z-score happens to fire more often during volatility regime
transitions where ATR-scaled stops and targets have favorable
hit-rate asymmetries.

### Reasoning
- Q9 showed only 8.4% overlap with top-5% volatility bars, but the
  hypothesis isn't "OMEN catches vol spikes" — it's "OMEN's exits
  are calibrated to a vol regime that happens to favor breakouts."
- The 2.0x ATR stop / 4.5x ATR target asymmetry creates an inherent
  positive expectancy in certain volatility environments regardless
  of entry quality.
- Sharpe-degradation pattern (IS 2.57 → OOS 0.51) might reflect
  volatility regime change between training and OOS windows.

### Operationalization for forward test
- Bucket forward sessions by realized volatility quartile
- Check if OMEN's edge is concentrated in specific vol buckets
- Test a control: same exits + random entries with same trigger rate
- If edge persists with random entries, mechanism is exit-driven not GEX-driven

---

## Hypothesis C — Mean-reversion at extreme flows

### Statement
The Q9 finding (z=3.0+ bucket Sharpe +3.05, z=1.8-2.0 bucket Sharpe
-2.75) is consistent with OMEN catching exhaustion-fade at extreme
flow events, not momentum continuation. The directional logic
(long on +z, short on -z) might be accidentally aligned with
reversion at extremes and continuation in the middle.

### Reasoning
- Q9 showed non-monotonic z-magnitude vs P&L pattern.
- The mid-range bucket (z=2.5-3.0) being weaker than both adjacent
  buckets is consistent with two different mechanisms acting in
  different z ranges.
- The Q4 MFE/MAE finding showed RUN_UP_THEN_FADE as modal — the
  signal catches real moves that then reverse. At extreme z, the
  reversal might BE the edge.

### Operationalization for forward test
- For each fresh-session OMEN signal, compute z-magnitude bucket
- Compute forward returns at multiple horizons (5m, 15m, 25m, 60m)
- Test if extreme-z signals show stronger mean-reversion signature
  than mid-z signals
- Pre-register specific tests for monotonicity vs bimodality

---

## Hypothesis D — Microstructure proxy via options flow

### Statement
Gexoflow_z and dexoflow_z function as indirect proxies for aggressive
ES order flow. The "mechanism" is OFI (order flow imbalance) in the
underlying, observed indirectly through options market activity that
responds to underlying flow with a lag.

### Reasoning
- Options dealers hedge their books based on ES flow. Large ES moves
  drive dealer hedging which appears as GEX flow.
- Q4 showed L2-style aggression filters at 30-second windows have
  real signal but decay by 15 minutes. OMEN's signal might be
  catching the same underlying OFI patterns via a slower, more
  averaged proxy.
- The L2 TRCB framework didn't help OMEN because both signals were
  measuring the same thing redundantly, not because L2 was useless.

### Operationalization for forward test
- For each fresh-session OMEN signal, compute OFI in the 5-min
  window before signal bar close
- Test correlation: signal magnitude vs OFI magnitude
- Test if OFI alone (without GEX) on the same bars would have
  produced similar trade selection
- This requires the MBP-10 cache infrastructure already built

---

## Hypothesis E — Real GEX mechanism, underpowered test

### Statement
The GEX mechanism is real, but the effect size is too small for 247
OOS trades to detect at conventional significance levels. The
permutation test result (p=0.27) reflects insufficient sample size,
not absent mechanism.

### Reasoning
- 247 trades is small for detecting modest effects (Sharpe < 1.0
  scale).
- The original IS Sharpe of 2.57 (bugfixed) is high enough that the
  effect, if real, should be detectable with more data.
- The pre-registered forward test will roughly double the OOS sample
  size if it runs for 30+ sessions.

### Operationalization for forward test
- Re-run the permutation test after the OMEN-minus-SL forward test
  completes, using the combined OOS + forward data
- If combined sample's p drops below 0.10, the underpowered
  hypothesis is supported
- If combined sample's p stays around 0.25+, this hypothesis is
  unsupported

---

## Hypothesis F — Data artifact or undetected look-ahead

### Statement
Three bugs have already been found in OMEN's infrastructure. There
may be a fourth subtle bug — possibly a feature that incorporates
forward-looking information inadvertently. The "edge" might
partially come from this artifact.

### Reasoning
- Three independent bugs in core files (features.py, backtest.py)
  is already concerning.
- The session-boundary bug specifically affected z-scores; another
  subtle z-score or alignment bug could exist.
- The permutation test would not necessarily catch this kind of
  artifact if the artifact survives feature shuffling.

### Operationalization for forward test
- Code audit of features.py and signal generation logic
- Specifically check: any feature that uses .shift(-N) or similar
  forward indexing
- Compare live (real-time) signal generation against backtest
  signal generation on the same bars
- If they disagree, the backtest contains look-ahead

---

## Forward-test framework

NONE of these hypotheses are tested on the consumed 160-session corpus.

The order of operations is:

1. OMEN-minus-SL forward test runs per pre-reg 9c1c22f
2. Verdict obtained at 30+ fresh sessions
3. IF verdict is PASS: investigate which of these hypotheses best
   explains the surviving edge using fresh data accumulated AFTER
   the verdict
4. IF verdict is FAIL: most hypotheses become moot (no edge to
   explain). Hypothesis F (look-ahead bug) becomes the priority —
   check whether the IS edge was real or artifact.

Hypotheses are ranked by my (Claude's, in this session) honest
prior probability that they explain OMEN:

  Hypothesis B (volatility regime / exits-driven): ~30%
  Hypothesis A (afternoon momentum): ~20%
  Hypothesis E (real GEX, underpowered): ~20%
  Hypothesis F (data artifact): ~15%
  Hypothesis D (OFI proxy): ~10%
  Hypothesis C (mean-reversion at extremes): ~5%

These are rough estimates and not used as test criteria. They're
for prioritization if multiple hypotheses get forward-tested.

## What this document does NOT authorize

- Consumed-data testing of any of these hypotheses
- Parameter changes to OMEN based on hypothesis speculation
- Modification of the OMEN-minus-SL pre-registered forward test
- Any deployment decision

## Sign-off

User verbal sign-off: given in chat session May 12-13, 2026.
Commit hash: `6f8b32d533c266899c1092e3de3e744db36aced6` (short: `6f8b32d`)
