# OOS 75-Day Baseline Validation — Pre-Registration

**Date locked:** 2026-04-29 (late night session, before any backtest run)
**Status:** LOCKED — no edits permitted after this commit
**Purpose:** Pre-commit evaluation criteria for OMEN's first true OOS test

---

## A — OOS Window Definition

- **Start:** 2025-09-08 (first available date in GexBot ES_SPX archive)
- **End:** 2025-12-23 (last trading day before in-sample window starts 2025-12-26)
- **Excluded:** 2025-11-27 (Thanksgiving), 2025-12-25 (Christmas)
- **Expected trading days:** ~75
- **Late-period OOS (2026-04-23 to 2026-04-28, ~4 days):** RESERVED, not run tonight
- **Held-out reserve from this 75-day window:** NONE (full window used for baseline)
- **Rationale:** Live forward sessions (post Zach fix) and late-period OOS provide held-out data for future filter testing

---

## B — Locked Configuration (DO NOT MODIFY)

- z_threshold: 1.8
- stop_atr_mult: 2.0
- target_atr_mult: 4.5
- feature_lookback_bars: 20
- atr_window_bars: 14
- trail_after_r: 0
- time_stop_min: 25
- blackout_lunch: True
- bar_freq: 5min

---

## C — Tonight's Scope (HARD CAP)

1. Verify run command and dependencies before execution
2. Run locked baseline on 75-day OOS window
3. Compute Tier 1 metrics: DSR, PSR, bar-level Sharpe
4. Log result against thresholds below
5. STOP. Sleep. No further analysis tonight.

---

## D — Verdict Thresholds (LOCKED)

### STRONG VALIDATION
ALL of:
- Forward DSR > 95%
- Daily-equity Sharpe ≥ 3.12 (within 30% of in-sample 4.45)
- Trade count between 130-220
- Profit factor > 1.5
- Total net PnL > $0
- Win rate ≥ 0.40

### MODERATE VALIDATION
ALL of:
- Forward DSR 70-95%
- Daily-equity Sharpe between 1.5 and 3.12
- Trade count between 100-250
- Profit factor > 1.2
- Total net PnL > $0
- Win rate ≥ 0.35

### FAILED VALIDATION
ANY ONE of:
- Forward DSR < 50%
- Daily-equity Sharpe < 1.0
- Total net PnL ≤ $0
- Profit factor < 1.0
- Trade count < 80 (signal firing too rarely)
- Trade count > 350 (signal firing too often = bug)

### AMBIGUOUS
- Forward DSR 50-70% with mixed signals on other metrics
- Treat as MODERATE-BORDERLINE

---

## E — Decision Tree by Verdict

### IF STRONG
- Tonight: log result, sleep
- Tomorrow: Tier 2 stratification (VIX, time-of-day, regime, day-of-week)
- This week: live forward test starts when Zach's fix lands (locked config, no changes)
- After 30+ live forward sessions: compute Tier 1 metrics again, compare to historical OOS verdict
- After BOTH historical OOS and live forward pass: carefully start tiny real money

### IF MODERATE
- Tonight: log result, sleep
- Tomorrow: Tier 2 stratification with extra-careful interpretation
- This week: live forward test starts but with smaller initial size assumption
- Strategy is alive but degraded; longer paper trade window required before any real money

### IF FAILED
- Tonight: log result, sleep
- Tomorrow: do NOT troubleshoot or "fix" the strategy
- First action: audit data integrity (verify OOS files valid, backtest engine applied identically)
- If integrity confirmed clean: strategy invalidated, project goes to feature exploration

### IF AMBIGUOUS
- Tonight: log result, sleep
- Tomorrow: Tier 2 stratification but treat every result as suspect
- Do NOT make STRONG/FAILED call from ambiguous data
- Wait for live forward sessions as tiebreaker

---

## F — Hard Prohibitions Tonight

DO NOT:
- Modify locked config
- Run any variant alongside baseline
- Add any filter (zcharm, RVOL, VIX bucket, anything)
- Re-run with different date ranges
- Re-interpret results to fit a narrative
- Make any decision before sleep
- Look at intermediate trade log entries during the run
- Run any Tier 2/3/4 test before reading Tier 1 verdict tomorrow

---

## G — Critical Reminders

- STRONG verdict ≠ deploy real money. Live forward test is still required.
- Locked config never changes based on this test alone.
- 75 OOS days is a one-shot resource. Tonight uses it once for baseline.
- Tomorrow rested > tonight tired for interpretation.

---

**End of pre-registration. Locked at commit time below.**
