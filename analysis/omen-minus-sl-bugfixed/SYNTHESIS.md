# OMEN-minus-SL bugfixed fresh-session quick-check (THROWAWAY)

Branch: `analysis/omen-minus-sl-bugfixed-quickcheck-throwaway` (throwaway / archive only; never merges to main).
Generated: 2026-05-12T22:43:18

## 1. Disclosure

## DISCLOSURE — fourth analysis on the same fresh sessions

This is a re-run of the OMEN-minus-SHORT_long quick-check on fresh
sessions, now using the bugfixed infrastructure (features.py
session-boundary fix + backtest.py time-stop and overlap fixes, all
merged to main).

These same fresh sessions have been used for:
1. Original quick-check (buggy code)
2. ATR=20 sensitivity variant
3. Zach's May params comparison
4. Now this bugfixed re-run

Cumulative consumption: 4 analyses on the same 8-9 sessions. The data
is no longer clean for forward-test purposes.

Sample size remains too small for any verdict (~16-20 trades expected).
Results inform planning only. Proper forward-test pre-registration on
30+ accumulated fresh sessions remains the required validation path.


## 2. Setup

- Fresh sessions analyzed: **8** (2026-04-30 → 2026-05-11)
  - Excluded: 2026-04-29 (GexBot `.missing` sentinel) and 2026-05-12 (ES 1s bars not yet pulled).
- Locked baseline params: z=1.8, blackout_lunch=True, stop=2.0×ATR, target=4.5×ATR, time_stop=25min, ATR=14, bar_freq=5min.
- Infrastructure: main with all three bug fixes (commits c333405 + c52a9ab).

## 3. Aggregate metrics on bugfixed fresh-session run

| arm | N | win | mean $ | sum $ | Sharpe | max DD |
|---|---:|---:|---:|---:|---:|---:|
| full_omen_bugfixed | 24 | 62.5% | $+14.53 | $+349 | +1.28 | $-914 |
| omen_minus_sl_bugfixed | 22 | 63.6% | $+31.36 | $+690 | +2.66 | $-914 |

## 4. Per-cell breakdown

| cell | N | mean $ | sum $ | Sharpe (if N≥10) |
|---|---:|---:|---:|---:|
| LONG_long | 3 | $+274.17 | $+822 | (n<10: n=3) |
| LONG_short | 9 | $+71.39 | $+642 | (n<10: n=9) |
| SHORT_long | 2 | $-170.62 | $-341 | (n<10: n=2) |
| SHORT_short | 10 | $-77.50 | $-775 | -3.54 |

### Exit-reason distribution (fresh, bugfixed)

| exit_reason | count |
|---|---:|
| time | 18 |
| stop | 5 |
| target | 1 |
| trail | 0 |
| session_close | 0 |

## 5. Six-way comparison

| sample | N | sessions | full Sharpe | minus-SL Sharpe | SHORT_long N | SHORT_long Sharpe |
|---|---:|---:|---:|---:|---:|---:|
| buggy IS | 174 | 80 | +5.38 | +4.36 | 32 | +3.23 |
| buggy OOS | 158 | 76 | +1.13 | +2.79 | 48 | -1.95 |
| bugfixed IS | 257 | 74 | +2.57 | +1.23 | 65 | +3.30 |
| bugfixed OOS | 247 | 72 | +0.51 | +1.88 | 68 | -1.70 |
| buggy fresh | 18 | 8 | +0.30 | +1.84 | 1 | (n=1) |
| **bugfixed fresh (this)** | **24** | **8** | **+1.28** | **+2.66** | **2** | **(n=2)** |

## 6. Honest interpretation

### Bugfixed code vs buggy code on the same fresh sessions

- Buggy fresh full Sharpe = +0.30 (n=18). 
  Bugfixed fresh full Sharpe = +1.28 (n=24). 
  Bugfixed code raises the fresh full Sharpe notably.

- Buggy fresh minus-SL Sharpe = +1.84 (n=17). 
  Bugfixed fresh minus-SL Sharpe = +2.66 (n=22). 
  Bugfixed code raises the fresh minus-SL Sharpe notably.

### Bugfixed fresh vs bugfixed historical OOS

- Bugfixed historical OOS (n=247, 72 sessions): full +0.51, minus-SL +1.88.
- Bugfixed fresh (n=24, 8 sessions): full +1.28, minus-SL +2.66.
  Fresh full Sharpe is in the same neighborhood as historical OOS.

### Cell-exclusion hypothesis on bugfixed fresh

- SHORT_long count on bugfixed fresh: **n=2**, sum=$-341, mean=$-170.62.

**The cell-exclusion result still rests on a tiny SHORT_long sample (n=2).** The minus-SL Sharpe lift (+1.28 → +2.66) is driven by 
removing 2 trade(s). On any specific tiny sample like this, 
this lift can move dramatically with a single different SHORT_long outcome — 
the hypothesis cannot be evaluated rigorously here.

By total $ damage, SHORT_short (n=10, sum=$-775) is contributing more drag than SHORT_long (n=2, sum=$-341) on this window. If the cell-exclusion 
hypothesis is right *in general*, the fresh sample isn't where to test it.

## 7. Decision-relevant findings

1. **Full OMEN bugfixed fresh (+1.28) vs bugfixed historical OOS (+0.51)**: 
   Differences are within the noise floor of n≈24 trade samples.

2. **SHORT_long count = 2 on bugfixed fresh.**
   The cell-exclusion hypothesis (OMEN-minus-SL > OMEN) cannot be rigorously 
   evaluated when the excluded cell has only 2 trade(s). 
   This holds regardless of which infrastructure produced the trades.

3. **Direction of cell-exclusion effect**: 
   `minus_sl_bugfixed Sharpe > full_omen_bugfixed Sharpe` (directionally consistent with the OOS-247 finding +1.88 > +0.51).

4. **What this analysis cannot tell us**: whether the cell-exclusion edge is real, 
   whether it generalizes beyond this window, whether the bugfixed infrastructure 
   changes the right cells. Forward-test pre-registration on 30+ accumulated fresh 
   sessions remains the only path to those answers.

## 8. Caveats (mandatory)

- **This is the fourth analysis on the same 8 fresh sessions** 
  (original quick-check, ATR=20 variant, Zach May, this bugfixed re-run). 
  These sessions are cumulatively consumed for the cell-exclusion hypothesis.
- **Sample size 24 trades / 8 sessions is far too small** for 
  any statistical verdict.
- **SHORT_long has n=2 on this sample**; whether the cell-exclusion 
  pattern survives is essentially undetermined by these trades.
- **No deployment decision is authorized by this analysis** regardless of how the 
  numbers look.
- **Forward-test pre-registration on 30+ accumulated unconsumed sessions** is the 
  only path to validation. That work has not yet begun.
