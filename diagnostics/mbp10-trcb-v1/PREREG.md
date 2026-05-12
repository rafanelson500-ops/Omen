# Pre-Registration: OMEN Three-Requirement Confirmed Breakout Filter
## TRCB-v1

**Status:** LOCKED — Gate 1 confirmed, user sign-off received in chat  
**Git branch:** `diagnostics/mbp10-trcb-filter-v1`  
**Scripts location:** `scripts/trcb_filter/`  
**Reports location:** `diagnostics/mbp10-trcb-v1/`  
**Date locked:** [FILL: commit timestamp]  
**Commit hash of this document:** [FILL: git hash]

---

## 1. Purpose

Test whether a three-requirement order-flow confirmation filter applied to OMEN's locked-baseline signal log materially improves out-of-sample performance on the existing 160-session corpus.

**This is a diagnostic test on consumed data.** A positive result earns the filter the right to forward-test on future sessions. It does not validate the strategy, does not constitute OOS evidence, and does not authorize changes to the locked OMEN config.

Source frameworks:
- Academic: Cont, Kukanov, Stoikov (2014) — OFI linear relationship with short-horizon price changes
- Practitioner: Brannigan Barrett / Axia Futures — "3 Requirements For A Confirmed Breakout" (volume + delta + price response, all three required)
- Prior work: V4.1 C6 (3:1 imbalance, single-tick, failed holdout) — this filter is the multi-requirement evolution

---

## 2. Hypothesis

OMEN signals followed within 75 seconds by simultaneous volume expansion, directional delta alignment, and positive price response will produce materially better trade outcomes than OMEN signals at large.

**Mechanism:** GEX burst identifies dealer hedging intent (the structural thesis). The three-requirement window tests whether that intent is materializing in the ES tape as a sustained drive vs. fading as an exhaustion/stop-run. Two independent sensors measuring the same underlying event. Agreement = higher confidence. Disagreement = signal is a fakeout.

This directly addresses the identified OOS failure mode: OMEN's signal fires on real GEX events, but ~62% of the time the immediate tape fades rather than drives, producing the 38% win rate and the OOS degradation.

---

## 3. Gate 1 — Data Requirement

**Required before any analysis runs:**

ES futures trade-level data with sub-second timestamps for the same 160 sessions as OMEN's trade log, including:
- Individual trade price
- Individual trade size (contracts)
- Trade timestamp (sub-second)
- Concurrent best bid and best ask at trade time (for midpoint classification)

**Trade side classification method:** Midpoint rule (identical to V4.1's C6 implementation in `src/v_flr_3/range_bars.py:122-128`)
- Trade price ≥ midpoint → aggressive buy
- Trade price < midpoint → aggressive sell  
- Trade price = midpoint exactly → aggressive buy (tie-breaker, E34 convention)
- Locked/crossed quote (bid = ask) → aggressive buy (midpoint collapses)

**If Gate 1 confirmed:** proceed.  
**If Gate 1 fails (snapshots only, no individual trade events):** this pre-reg is void. Return to concept selection before writing any code.

**Gate 1 status:** CONFIRMED — User confirmed MBP-10 data source is Databento MBP-10 schema, which includes individual trade events with sub-second timestamps and concurrent NBBO. Midpoint rule classification is implementable as specified.

---

## 4. Locked Parameters

All four parameters are locked before any analysis runs. They may not be adjusted based on observed results. Any change requires a new pre-reg document with a new commit timestamp.

### P1 — Detection Window Length
**60 seconds** post signal-bar-close.

Rationale: Round number matching the academic OFI literature horizon (Cont/Kukanov/Stoikov 2014 operate at tens-of-seconds to one-minute scale; the 2025 E-mini SVAR paper confirms shock decay at this horizon). Long enough to see whether post-burst aggression sustains beyond a single-tick flick. Short enough to make an entry decision before meaningful directional drift develops.

### P2 — Volume Threshold
Directional aggressive volume during window ≥ **1.0×** the trailing 100-bar median directional aggressive volume per equivalent 60s window.

Definition of "directional aggressive volume": sum of all trade contract sizes during the 60s window where trade side = OMEN's signal direction (aggressive buys for long signals; aggressive sells for short signals).

Definition of "trailing 100-bar median": for each of the 100 5-minute bars preceding the signal bar, compute total directional aggressive volume in the 60s window following that bar's close. Take the median of those 100 values.

Rationale: 1.0× tests "volume did not go quiet in the signal direction" — the failure mode this catches is post-burst silence (aggression event happened, then nothing). Asking for elevated volume (1.5×+) confuses two different mechanisms — the GEX signal already implies elevated volume; P2 should test that flow continues normally, not that it ramps further. Mechanism = continuation check, not exception check.

### P3 — Delta Ratio Threshold
(Directional aggressive volume) / (opposite aggressive volume) during window ≥ **2.0:1**

For long signals: (aggressive buy volume) / (aggressive sell volume) ≥ 2.0  
For short signals: (aggressive sell volume) / (aggressive buy volume) ≥ 2.0

Divisor floor: 1 contract (consistent with V4.1 E34 defensive default — methodological continuity).

Rationale: 2.0:1 is less demanding than V4.1's C6 3.0:1 ratio at single-tick. The reduced threshold is appropriate here because the ratio is computed over a full 60s window — tick-level noise averages out, so a sustained 2:1 is mechanically harder to produce by chance than a single 3:1 print. Strongest single mechanism in the filter; not diluted.

### P4 — Price Response Threshold
Net signed price move during window ≥ **0.25 × ATR at signal entry** in signal direction.

For long signals: (price_at_window_end − price_at_signal_bar_close) ≥ 0.25 × ATR_entry  
For short signals: (price_at_signal_bar_close − price_at_window_end) ≥ 0.25 × ATR_entry

ATR source: OMEN's locked ATR value at exact moment of entry, as stored in the existing trade log. ATR computed with `atr_window_bars=14` per user confirmation (IS-OOS sensitivity test showed minimal impact).

Rationale: Direction-confirmation mechanism, not magnitude. P2 (volume) and P3 (delta) carry the strength signals — P4 needs only to confirm that price actually moved in signal direction. 0.25 × ATR over 60 seconds is meaningful directional movement without requiring exceptional velocity (0.5 × ATR would imply 5× normal directional speed, which is unreasonably demanding). Eliminates cases where high volume occurs but price goes nowhere (opposing absorption).

---

## 5. Filter Logic

A trade is **FILTER-CONFIRMED** if and only if ALL THREE conditions hold simultaneously during the 60-second window:

```
condition_1 (P2): directional_aggressive_volume_in_60s_window >= 1.0 * trailing_100bar_median

AND

condition_2 (P3): directional_aggressive_volume / opposite_aggressive_volume >= 2.0

AND

condition_3 (P4): signed_price_move_in_60s_window >= 0.25 * atr_at_entry
```

Boolean AND. All three must pass. Partial credit does not exist. Two of three = FILTER-REJECTED.

A trade is **FILTER-REJECTED** if any one of the three conditions fails.

---

## 6. Phase 2 — Population-Level Pre-Condition

**This step runs before applying the filter to OMEN's trade log.**

Run the three-requirement detector on every 5-minute bar in the 160-session corpus (not just OMEN's signal bars — all bars). For each bar where all three requirements trigger, compute the 25-minute forward return (matching OMEN's time-stop horizon) signed by the direction the three requirements implied. The 60-second window starts at the close of each 5-minute bar.

**Pre-registered checkpoint:**
- If the population of "all-three-triggered" bars shows mean 25-min forward return that is directionally positive and materially different from the unconditional population mean: **proceed to Phase 3.**
- If no population-level directional signal is detectable: the filter sensor lacks empirical support at OMEN's timeframe. Document the null result and halt. Do not apply to OMEN's trade log.

Purpose: validate that the sensor has any predictive power before trusting it on OMEN's small trade sample. Failure here means the filter mechanism is invalid, not that the parameters are wrong.

---

## 7. Window Alignment and Look-Ahead Note

OMEN generates signals at bar close and enters at the OPEN of the next bar (next-bar execution to prevent look-ahead bias per locked spec).

The TRCB filter's 60-second window begins at signal-bar-close, which overlaps with the first 60 seconds of the entry bar.

**In live trading:** filter imposes a 60-second delay from bar-open before entering. This is not look-ahead — we observe 60 seconds of tape, then decide. Entry would be ~60 seconds later than OMEN's assumed open-of-bar entry.

**For this diagnostic on historical data:** we apply the filter post-hoc to the existing trade log. The entry price in the trade log (bar open) precedes the filter window. This creates a minor discrepancy: in live trading the fill would be ~60 seconds after bar open at a potentially different price. We flag this explicitly but do not attempt to correct for it in this diagnostic. Correction is required in forward-test implementation.

**Implication for slippage:** the 60-second delay may improve or worsen fill quality depending on the 60-second price path. This is an unresolved variable. Flag for forward-test design, not blocking here.

---

## 8. Application to OMEN Trade Log

Apply filter to:
- **IS corpus:** all 174 in-sample trades (80 sessions, Dec 26 2025 – ~Apr 22 2026 per project records)
- **OOS corpus:** all OOS trades (75 sessions — exact count from trade log)

For each trade: query the MBP-10 trade data for the 60-second window post signal-bar-close. Evaluate all three conditions. Assign FILTER-CONFIRMED or FILTER-REJECTED tag. Store the three individual condition results alongside the binary verdict for diagnostics.

---

## 9. Reporting Structure

Report all three buckets in a single document. Do not report selectively.

| Bucket | N total | N confirmed | Confirm rate | Sharpe total | Sharpe confirmed | Win rate total | Win rate confirmed | Max DD total | Max DD confirmed |
|--------|---------|-------------|-------------|-------------|-----------------|-------------|------------------|-------------|-----------------|
| IS-80  | | | | | | | | | |
| OOS-75 | | | | | | | | | |
| Combined | | | | | | | | | |

Additional required reporting:
- Most common rejection reason (which of P2/P3/P4 fails most often, and by how much it missed threshold on average)
- Time-of-day distribution: confirmed vs. rejected signal counts by hour bucket (09:30, 10:30, 11:00, 13:00, 14:00, 15:00)
- Side distribution: long signals confirmed vs. rejected; short signals confirmed vs. rejected
- Regime distribution (VIX buckets if available): confirm rate by VIX regime

---

## 10. Pre-Registered Success Criteria

**Primary criteria — BOTH must be satisfied simultaneously for a PASS verdict:**

1. OOS-75 filtered Sharpe ≥ **1.20** (unfiltered OOS Sharpe 0.70 + 0.50 minimum lift)
2. OOS-75 confirmation rate ≥ **40%** (filter retains at least 40% of OOS trades; with ~75 OOS trades this means ≥ 30 confirmed trades minimum for any statistical meaning)

**Marginal zone — defaults to FAIL:**
- OOS filtered Sharpe 0.90–1.19 AND confirmation rate ≥ 40% → MARGINAL → FAIL
- OOS filtered Sharpe ≥ 1.20 AND confirmation rate 25–39% → MARGINAL → FAIL

**FAIL:** anything not meeting both primary criteria simultaneously.

No "almost passed" interpretation. Marginal defaults to FAIL per project discipline.

---

## 11. Decision Rules Post-Result

| Outcome | Action |
|---------|--------|
| PASS | Filter documented in `diagnostics/mbp10-trcb-v1/`. Added to candidate forward-test config list. Evaluated at session-30 review alongside locked-config forward-test results. Locked OMEN config is NOT modified. |
| FAIL | Result fully documented. Concept archived in project "tested and dead" list. May not be re-tested with adjusted thresholds on this data. Requires genuinely new data (forward sessions not in the 160-session corpus) for any revisit. |
| MARGINAL (defaults to FAIL) | Same action as FAIL. |

---

## 12. Git Discipline

```
Branch:   diagnostics/mbp10-trcb-filter-v1
Scripts:  scripts/trcb_filter/
Reports:  diagnostics/mbp10-trcb-v1/
```

**Files that may not be touched by this work under any circumstances:**
`cheese/`, `strategy.py`, `backtest.py`, `market.py`, `gex.py`, `features.py`, locked config file

This pre-reg document is committed to the branch at the start of work. The commit timestamp of this document is the analysis start gate. No analysis runs before this document is committed.

---

## 13. Open Items Before Analysis Begins

| # | Item | Status |
|---|------|--------|
| 1 | **Gate 1:** Confirm MBP-10 data includes individual trade events with side-classifiable prices | ✅ CONFIRMED — Databento MBP-10 schema |
| 2 | **ATR mismatch:** Confirm whether trade log used `atr_window_bars=14` or `=20` for parameter P4 | ✅ NOTED — User confirms ATR=14, IS-OOS sensitivity test showed minimal impact |
| 3 | **FLOW_Z_WINDOW mismatch (60 bars vs documented 20):** Pre-reg does not depend on this parameter directly, but the trade log was generated under the 60-bar condition. | NOTED — to be flagged in report for completeness |

---

## 14. User Sign-Off

By proceeding with analysis, the user confirms:

- Parameters P1–P4 are locked as specified above and will not be changed based on results
- The data gate (Gate 1) has been confirmed satisfied
- All three reporting buckets will be published regardless of outcome
- The decision rules in Section 11 will be followed

**Sign-off:** ✅ User stated "use ur revisions, lets start" in chat following parameter re-examination and revision approval  
**Date locked:** 2026-05-12  
**Commit hash of this document:** [FILL after `git add` + `git commit`]

---

*Document version: v1.1 — LOCKED*  
*v1.0 (initial draft): P1=75s, P2=1.5×, P3=2.0:1, P4=0.5×ATR — not committed*  
*v1.1 (locked): P1=60s, P2=1.0×, P3=2.0:1, P4=0.25×ATR — final parameters after Brannigan transcript re-analysis and internal consistency check*  
*Based on: Axia Futures "3 Requirements For A Confirmed Breakout" transcript; Brannigan Barrett Initiative Drive transcript; Cont/Kukanov/Stoikov (2014); 2025 E-mini SVAR paper; project V4.1 C6 post-mortem; OMEN OOS diagnostic tiers 1–5*
