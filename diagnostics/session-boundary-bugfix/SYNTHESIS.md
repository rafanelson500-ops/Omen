# Session-boundary bug fix — IS / OOS re-run impact

Branch: `diagnostics/session-boundary-bugfix` (diagnostics branch; merge to main only with explicit user sign-off).
Generated: 2026-05-12T22:05:58

## 1. What the bug was

`backend/cheese/features.py` computed rolling ATR (window=14), rolling 
flow z-scores (window=60), `dist_z_mlgamma` sign-cross detectors, and 
wall-break detectors **without resetting at session boundaries**. In a 
multi-day historical backtest, the first ~14-20 bars of every session 
inherited the *previous session's tail* into their rolling statistics: 
(a) ATR's first bars used yesterday's close as `prev_close`, so the 
overnight gap counted as an enormous true range — inflating ATR for ~14 
bars; (b) the rolling 60-bar gexoflow/dexoflow z-score rolled into 
yesterday's distribution — inflated StdDev → *suppressed* z-score 
magnitudes near session start, so legitimate signal bars were measured 
relative to overnight volatility and never reached the 1.8 threshold. 
Crossing detectors fired on the first bar of day N if it opened across 
yesterday's wall, regardless of any actual intraday cross.

**Bug-impact zones**:
- **ATR(14)**: at 5-min bars, 14 bars = ~1 hour. ATR is contaminated for the 
  first ~14 bars (~70 minutes) of each session, then settles to within-session.
- **Flow z-score (window=60)**: at 5-min bars, 60 bars = 5 hours, which is 
  *longer than the 6.5-hour RTH session*. The rolling window NEVER fully 
  populates within a single session — so for the bug version, the z-score 
  baseline is *always* dragged by previous-session tail data, throughout 
  the entire RTH session.

This is why the first-20-bars trade-count change in the table below is 
nearly zero (the trades shifted around, not concentrated in early bars) 
but the *total* trade count jumped 50-60%: the bug affected z-score-driven 
entry decisions throughout each session, not just at the open.

## 2. What the fix does

Replaces every `Series.rolling(...)` / `Series.shift(1)` in features.py 
with the per-session-grouped variant: `Series.groupby(session_date)`.
transform(rolling) and `.groupby(session_date).shift(1)`. The first bar 
of every session sees only that session's data — exactly equivalent to 
running a stack of single-day backtests glued together. Identical to 
Zach's diff `git diff main zach/main -- backend/cheese/features.py`. 
No other locked files are modified.

## 3. Side-by-side IS / OOS impact (locked params, only features.py changed)

| metric | IS orig | IS bugfixed | Δ | OOS orig | OOS bugfixed | Δ |
|---|---:|---:|---:|---:|---:|---:|
| N trades | 174 | 262 | +88 | 158 | 252 | +94 |
| Win rate | 48.9% | 48.1% | -0.8 pp | 48.7% | 46.8% | -1.9 pp |
| Mean $ | $+141.66 | $+66.16 | $-75.50 | $+26.29 | $+7.03 | $-19.26 |
| Sum $ | $+24649 | $+17334 | $-7315 | $+4154 | $+1771 | $-2382 |
| **Sharpe** | **+5.38** | **+3.34** | **-2.03** | **+1.13** | **+0.40** | **-0.72** |
| Max DD $ | $-2594 | $-4289 | $-1695 | $-4642 | $-6425 | $-1782 |
| Sessions | 73 | 74 | — | 72 | 72 | — |
| First-20-bar trades | 40 | 39 | -1 | 38 | 37 | -1 |

## 4. Per-cell impact

### IS — original vs bugfixed

| cell | orig N | orig Sharpe | fixed N | fixed Sharpe | Δ Sharpe |
|---|---:|---:|---:|---:|---:|
| LONG_long | 44 | +1.54 | 67 | +1.10 | -0.44 |
| LONG_short | 45 | +5.05 | 68 | +2.83 | -2.22 |
| SHORT_long | 43 | +3.23 | 63 | +4.38 | +1.14 |
| SHORT_short | 42 | +0.78 | 64 | -2.10 | -2.88 |

### OOS — original vs bugfixed

| cell | orig N | orig Sharpe | fixed N | fixed Sharpe | Δ Sharpe |
|---|---:|---:|---:|---:|---:|
| LONG_long | 33 | +2.11 | 66 | +0.80 | -1.31 |
| LONG_short | 29 | +2.07 | 46 | +3.00 | +0.94 |
| SHORT_long | 48 | -1.95 | 70 | -2.14 | -0.19 |
| SHORT_short | 48 | +1.01 | 70 | +0.07 | -0.94 |

## 5. Trade-level overlay (matched on entry_time + side + gamma_regime)

| sample | matched | only-orig | only-fixed | matched same exit | Δ net mean (both) | Δ net sum (both) |
|---|---:|---:|---:|---:|---:|---:|
| IS | 161 | 13 | 101 | 161/161 | $+0.00 | $+0 |
| OOS | 151 | 7 | 101 | 151/151 | $+0.00 | $+0 |

## 6. OMEN-minus-SL Sharpe under bugfixed features

| sample | full Sharpe (orig) | full Sharpe (fixed) | minus-SL Sharpe (orig) | minus-SL Sharpe (fixed) |
|---|---:|---:|---:|---:|
| IS  | +5.38 | +3.34 | +4.36 | +1.44 |
| OOS | +1.13 | +0.40 | +2.79 | +2.03 |

**Does the cell-breakdown finding (OOS SHORT_long Sharpe = −1.95) replicate under bugfixed features?**
- OOS SHORT_long orig: n=48, Sharpe = -1.95, sum = $-4165
- OOS SHORT_long fixed: n=70, Sharpe = -2.14, sum = $-5438
- **Cell-breakdown finding REPLICATES under bugfixed features.** SHORT_long 
  remains negative-Sharpe on OOS and minus-SL still outperforms full OMEN.

## 7. Honest impact assessment

- **IS Sharpe change**: +5.38 → +3.34 (Δ -2.03, -37.8%)
- **OOS Sharpe change**: +1.13 → +0.40 (Δ -0.72, -64.1%)

**Verdict: bug was LOAD-BEARING.** Sharpe shifts >30% on at least one 
sample. All prior conclusions need re-examination under bugfixed features. 
Trade counts changed materially — the pre-fix locked baseline was running 
on a *suppressed* signal set, not the intended one.

## 8. Decision points for the user

1. **Should the locked baseline be updated with the fix?**
   - Pro: features.py was unambiguously buggy. Every prior analysis ran on 
     contaminated z-scores and ATR near session opens.
   - Pro: identical to Zach's fork's session-boundary fix — both teams 
     converged on the same correction.
   - Con: every previously committed baseline number (locked Sharpe 4.45, 
     OOS 1.13, cell breakdown Sharpes, OMEN-minus-SL 2.79) was computed on the 
     pre-fix features. Updating means re-running and re-committing those numbers.
   - Con: prior pre-registered tests (TRCB-v1 pre-reg) reference the pre-fix 
     baseline. Those pre-regs were validated against the wrong feature pipeline.

2. **Do prior pre-registered tests need to be re-done?**
   - TRCB-v1 used per_bar_volumes computed independently from MBP-10 trades, 
     so the session-boundary bug did NOT affect its per-bar volumes. However, 
     the comparison baseline (OMEN's gexoflow/dexoflow) WAS affected. Any 
     conclusion that compared TRCB to OMEN should be re-checked.
   - Q1-Q4 post-mortem and Q6-Q8 component diagnostics used the same 
     per-bar volumes table; their conclusions are mechanically the same. 
     The Q3 'TRCB framework signals decay' finding still holds.
   - The original cell-breakdown (the basis for OMEN-minus-SL) was computed 
     on pre-fix trade logs. Its replication status under the fix is shown in 
     section 6 — read that before relying on the cell breakdown.

3. **How does this affect the planned OMEN-minus-SL forward test?**
   - Bugfixed OOS shows minus-SL Sharpe > full Sharpe. Hypothesis 
     direction survives the fix. Forward test still worth pre-registering 
     — but the pre-reg should be written against the bugfixed baseline.

## 9. Caveats

- The session-boundary fix changes EVERY z-score-driven bar's feature values 
  within an RTH session, because the 60-bar flow z-score rolling window is 
  longer than RTH itself. ATR's contamination is shorter-lived (first ~14 
  bars per session).
- Trade counts changed dramatically — bugfixed corpus is 50%+ larger on IS, 
  60%+ larger on OOS. The two samples are NOT comparable as 'same backtest, 
  different ATR/z formulas' — they are *different trade sets*.
- The decision to merge to main is the user's. This synthesis presents the 
  impact; it does NOT auto-merge.
- Prior pre-registered analyses on the consumed 160-session corpus are not 
  auto-invalidated by the fix; some (Q3, post-mortem) are based on per-bar 
  MBP-10 volumes that are independent of features.py. Others (cell breakdown, 
  OMEN-minus-SL quick-check) used OMEN trade logs and would need re-running.
