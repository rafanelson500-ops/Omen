# All-bugfixes baseline — IS / OOS impact (three-way)

Branch: `diagnostics/all-bugfixes-baseline` (diagnostics; merge to main only with explicit user sign-off).
Generated: 2026-05-12T22:21:19

## 1. Bug fixes applied (vs `main`)

`main` already includes the **features.py session-boundary fix** (commit c333405). 
This branch adds the two remaining `backtest.py` fixes from Zach's Omen 2.0 fork:

- **FIX 1 — Time-stop off-by-one**: change time-stop trigger from `bars_in >= max_bars` to `bars_in >= max(1, max_bars - 1)`. Reason: exits fill at next-bar open, so triggering at `bars_in == max_bars` produces a `max_bars × bar_freq + bar_freq` realized hold instead of the intended `max_bars × bar_freq`. With time_stop_min=25 and 5min bars, the bug held trades for 30 min instead of 25.
- **FIX 2 — Exit/entry same-iteration block**: add `exit_occurred` flag; block the entry block on the same iteration that an exit fires. Reason: without this, a trade that exits at iteration `i` and a signal that fired at `i - 1` can produce a new entry at `o[i]`, BEFORE the just-resolved exit. Live cannot produce that; backtest could.

**NOT applied** (per spec): TRADE_START_TIME hard floor, z_threshold/stop/target/time_stop/lookback/trail parameter changes. All locked baseline parameters held: z=1.8, stop=2.0×ATR, target=4.5×ATR, time_stop=25min, ATR=14, lookback=20, blackout_lunch=True, bar_freq=5min.

## 2. Three-way comparison — IS (2025-12-30 → 2026-04-21)

| metric | original (no fixes) | + session-boundary | + all bugfixes |
|---|---:|---:|---:|
| N trades | 174 | 262 | 257 |
| Win rate | 48.9% | 48.1% | 49.4% |
| Mean $ | $+141.66 | $+66.16 | $+47.24 |
| Sum $ | $+24649 | $+17334 | $+12140 |
| **Sharpe** | +5.38 | +3.34 | +2.57 |
| Max DD $ | $-2594 | $-4289 | $-3639 |
| Mean bars_held | 4.83 | 4.99 | 4.31 |
| Mean hold (min) | 24.17 | 24.94 | 21.54 |
| Trade overlaps | 10 | 17 | 0 |

## 3. Three-way comparison — OOS (2025-09-08 → 2025-12-23)

| metric | original (no fixes) | + session-boundary | + all bugfixes |
|---|---:|---:|---:|
| N trades | 158 | 252 | 247 |
| Win rate | 48.7% | 46.8% | 45.3% |
| Mean $ | $+26.29 | $+7.03 | $+8.28 |
| Sum $ | $+4154 | $+1771 | $+2046 |
| **Sharpe** | +1.13 | +0.40 | +0.51 |
| Max DD $ | $-4642 | $-6425 | $-6719 |
| Mean bars_held | 5.14 | 5.23 | 4.46 |
| Mean hold (min) | 25.70 | 26.13 | 22.31 |
| Trade overlaps | 10 | 19 | 0 |

## 4. What each fix did (isolated effects)

### FIX 1 effect — time-stop off-by-one

Compare `+session-boundary` → `+all bugfixes` (FIX 1 + FIX 2 added):

- IS mean bars_held: 4.99 → 4.31 bars (24.9min → 21.5min hold). 
  Shorter holds confirm FIX 1 is firing the time-stop one bar earlier.
- OOS mean bars_held: 5.23 → 4.46 bars (26.1min → 22.3min hold).

### FIX 2 effect — exit/entry same-iteration block

Compare trade overlap counts at each stage:

- IS overlaps:  original=10, +session-boundary=17, +all bugfixes=0
- OOS overlaps: original=10, +session-boundary=19, +all bugfixes=0

**FIX 2 eliminated all trade overlaps.** No remaining trades enter while a 
prior trade is open — backtest is now live-equivalent on this dimension.

Trade-count reduction from FIX 2:
- IS:  262 → 257 trades (-5). The dropped trades are precisely the overlapping ones, plus a small number 
  shifted by FIX 1's earlier exits cascading into different next-bar entry windows.
- OOS: 252 → 247 trades (-5).

## 5. Exit-reason distribution

### IS

| exit_reason | original | +session-boundary | +all bugfixes |
|---|---:|---:|---:|
| time | 112 | 181 | 198 |
| stop | 42 | 61 | 49 |
| target | 15 | 15 | 10 |
| session_close | 5 | 5 | 0 |

### OOS

| exit_reason | original | +session-boundary | +all bugfixes |
|---|---:|---:|---:|
| time | 117 | 192 | 201 |
| stop | 29 | 47 | 39 |
| target | 7 | 8 | 7 |
| session_close | 5 | 5 | 0 |

## 6. Per-cell OOS Sharpe — three-way

| cell | orig N | orig Sh | +sb N | +sb Sh | +all N | +all Sh |
|---|---:|---:|---:|---:|---:|---:|
| LONG_long | 33 | +2.11 | 66 | +0.80 | 66 | +0.75 |
| LONG_short | 29 | +2.07 | 46 | +3.00 | 45 | +2.37 |
| SHORT_long | 48 | -1.95 | 70 | -2.14 | 68 | -1.70 |
| SHORT_short | 48 | +1.01 | 70 | +0.07 | 68 | +0.42 |

## 7. OMEN-minus-SL Sharpe under each baseline

| sample | orig | +session-boundary | +all bugfixes |
|---|---:|---:|---:|
| IS full | +5.38 | +3.34 | +2.57 |
| IS minus-SL | +4.36 | +1.44 | +1.23 |
| OOS full | +1.13 | +0.40 | +0.51 |
| OOS minus-SL | +2.79 | +2.03 | +1.88 |

## 8. Honest impact assessment

The honest baseline (all known bugs fixed, locked params untouched) is:

- **IS  Sharpe = +2.57** (n=257 trades, 74 sessions)
- **OOS Sharpe = +0.51** (n=247 trades, 72 sessions)

Compare to the originally-cited locked baseline (IS +5.38, OOS +1.13). The 
originally-cited numbers were inflated by both bugs working together: the 
session-boundary bug suppressed entries throughout the session, and the 
time-stop / overlap bugs together held winning trades 30min instead of 25min 
while letting overlapping entries pad PnL.

### Cell-breakdown / OMEN-minus-SL replication

OOS SHORT_long Sharpe under all-bugfixes: **-1.70** 
(remains negative). OMEN-minus-SL OOS Sharpe: **+1.88** vs full **+0.51** (> full → hypothesis direction survives).

## 9. Decision points for the user

1. **Update the locked baseline numbers to the all-bugfixes values?** 
   The honest IS/OOS Sharpes are what an aligned backtest/live system would 
   actually produce. Any cited Sharpe in future documentation should reference 
   the bugfixed numbers, not the pre-fix originals.
2. **Merge backtest.py fixes to main?** Both fixes are unambiguous backtester 
   bugs that diverge from live behavior. There is no scenario where keeping 
   the bugs is desirable. The remaining question is just whether you want to 
   bundle them with any other changes before merging.
3. **Re-cite prior analyses against the new baseline?** Same answer as the 
   session-boundary fix synthesis: the per-bar / per-trigger analyses 
   independent of backtest.py (Q3 / TRCB pop validation) stand; the trade-log 
   analyses (cell breakdown, OMEN-minus-SL quick-check, ATR=20 sensitivity, 
   Zach May comparison) used the buggy trade logs and would re-run with 
   different magnitudes if redone against the bugfixed baseline.

## 10. Caveats

- Two of three bugs fixed in this branch are EXIT-LOGIC bugs (FIX 1: time-stop 
  timing; FIX 2: overlap prevention). They do not change which signals fire — 
  the signal count is identical between +session-boundary and +all bugfixes 
  (0 signals 
  the same on both). The trade-count and Sharpe differences come from which 
  trades the backtester *allows* (FIX 2) and how long it holds them (FIX 1).
- These results are still on the now-thoroughly-consumed 160-session corpus. 
  Any new pre-registration should use this bugfixed baseline as its reference 
  point, not the pre-fix numbers.
- Forward-test validation on fresh sessions remains the only path to a verdict 
  on OMEN's edge. The all-bugfixed baseline is the honest starting point for 
  framing that test, not a substitute for it.
- This branch holds at `diagnostics/all-bugfixes-baseline`. Merge to main only 
  with explicit user sign-off.
