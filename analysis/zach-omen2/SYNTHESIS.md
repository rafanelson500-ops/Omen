# Zach Omen 2.0 vs locked bugfixed baseline — head-to-head

Branch: `analysis/zach-omen2-full-comparison-throwaway` (throwaway / archive only; never merges to main).
Generated: 2026-05-12T22:28:44

## 1. Disclosure

This is exploratory comparison of Zach's Omen 2.0 against the
honest bugfixed locked baseline on the same consumed IS/OOS corpus.
Both models use the same bugfixed infrastructure (features.py
session-boundary fix, backtest.py time-stop and overlap fixes).
Parameter differences are what's being compared. Results are
in-sample for both models — neither has been forward-tested on
clean data. No deployment decision should be made based on this
comparison alone.


## 2. Parameter difference summary

| param | locked (bugfixed) | Zach Omen 2.0 |
|---|---|---|
| z_threshold | 1.8 | **2.0** |
| blackout_lunch | True | **False** |
| TRADE_START_TIME | n/a | **12:30 ET** |
| stop_atr_mult | 2.0 | **1.5** |
| target_atr_mult | 4.5 | **2.5** |
| trail_after_r | 0 | **1.0** (trailing ON) |
| time_stop_min | 25 | **30** |
| atr_window_bars | 14 | 14 (same) |
| feature_lookback_bars | 20 | 60 (informational) |
| bar_freq | 5min | 5min |

Both models run on:
- Same IS window: 2025-12-30 → 2026-04-21
- Same OOS window: 2025-09-08 → 2025-12-23
- Same bugfixed infrastructure (commits c333405, c52a9ab on main)

## 3. Side-by-side performance

### IS (2025-12-30 → 2026-04-21)

| metric | locked | Zach | Δ |
|---|---:|---:|---:|
| N trades | 257 | 220 | -37 |
| Win rate | 49.4% | 39.5% | -9.9 pp |
| Mean $ | $+47.24 | $+2.93 | $-44.31 |
| Sum $ | $+12140 | $+644 | $-11496 |
| **Sharpe** | **+2.57** | **+0.17** | **-2.41** |
| Max DD $ | $-3639 | $-4535 | $-896 |
| Mean bars_held | 4.31 | 3.74 | -0.57 |
| Minus-SL Sharpe | +1.23 | -0.88 | -2.11 |

### OOS (2025-09-08 → 2025-12-23)

| metric | locked | Zach | Δ |
|---|---:|---:|---:|
| N trades | 247 | 215 | -32 |
| Win rate | 45.3% | 40.9% | -4.4 pp |
| Mean $ | $+8.28 | $-14.62 | $-22.91 |
| Sum $ | $+2046 | $-3144 | $-5190 |
| **Sharpe** | **+0.51** | **-0.86** | **-1.37** |
| Max DD $ | $-6719 | $-10776 | $-4058 |
| Mean bars_held | 4.46 | 3.98 | -0.48 |
| Minus-SL Sharpe | +1.88 | +0.62 | -1.26 |

## 4. Key diagnostic findings

### (a) Does the 12:30 start time eliminate morning losing trades?

Time-of-day split on the **locked** model (Zach's model fires only after 12:30 by design):

| period | sample | n | Sharpe | mean $ | sum $ |
|---|---|---:|---:|---:|---:|
| pre-12:30 | IS | 39 | +0.43 | $+29.46 | $+1149 |
| post-12:30 | IS | 218 | +2.81 | $+50.42 | $+10991 |
| pre-12:30 | OOS | 37 | +1.37 | $+83.68 | $+3096 |
| post-12:30 | OOS | 210 | -0.32 | $-5.00 | $-1050 |

Pre-12:30 trades total $+4245; post-12:30 total $+9941. 
Zach's 12:30 filter excludes the pre-12:30 set entirely.

### (b) Does SHORT_long still appear broken in Zach's model?

OOS SHORT_long: locked n=68 Sh=-1.70, sum $-3978; Zach n=60 Sh=-2.50, sum $-5025.
**Yes** — SHORT_long remains negative-Sharpe under both models. The 
12:30 filter and tighter exits don't fix the SHORT_long cell.

### (c) Does the trailing stop improve outcomes?

Trailing-stop exits in Zach's runs: IS=0, OOS=0.
Zero trailing-stop exits fired. Either (i) the trailing stop never armed 
(no trade ever reached +1R before being exited by another rule), or 
(ii) backtest.py logs ratcheted-stop exits as 'stop' rather than 'trail'. 
Check exit-reason taxonomy in backtest.py if attribution matters.

### (d) Tighter target (2.5×ATR vs 4.5×ATR): win rate vs avg win tradeoff

| sample | locked win_rate | Zach win_rate | locked mean $ | Zach mean $ |
|---|---:|---:|---:|---:|
| IS  | 49.4% | 39.5% | $+47.24 | $+2.93 |
| OOS | 45.3% | 40.9% | $+8.28 | $-14.62 |


### (e) IS→OOS consistency

- **Locked**:  IS +2.57 → OOS +0.51  
  = -80.0% Sharpe degradation
- **Zach**: IS +0.17 → OOS -0.86  
  = -613.4% Sharpe degradation

**Locked baseline degrades less** by ~533 pp. 
Zach's tighter parameters may be more overfit to the IS window.

## 5. Per-cell breakdown comparison

### IS

| cell | locked N | locked Sh | Zach N | Zach Sh |
|---|---:|---:|---:|---:|
| LONG_long | 65 | +1.11 | 51 | -0.47 |
| LONG_short | 66 | +1.95 | 56 | +1.10 |
| SHORT_long | 65 | +3.30 | 57 | +2.08 |
| SHORT_short | 61 | -1.46 | 56 | -2.66 |

### OOS

| cell | locked N | locked Sh | Zach N | Zach Sh |
|---|---:|---:|---:|---:|
| LONG_long | 66 | +0.75 | 56 | -0.78 |
| LONG_short | 45 | +2.37 | 44 | +3.18 |
| SHORT_long | 68 | -1.70 | 60 | -2.50 |
| SHORT_short | 68 | +0.42 | 55 | -0.97 |

## 6. Exit-reason distribution

| exit_reason | locked IS | Zach IS | locked OOS | Zach OOS |
|---|---:|---:|---:|---:|
| time | 198 | 90 | 201 | 98 |
| stop | 49 | 100 | 39 | 86 |
| target | 10 | 30 | 7 | 31 |
| trail | 0 | 0 | 0 | 0 |
| session_close | 0 | 0 | 0 | 0 |

## 7. IS→OOS consistency comparison

| model | IS Sharpe | OOS Sharpe | Δ pts | % degradation |
|---|---:|---:|---:|---:|
| Locked (bugfixed) | +2.57 | +0.51 | -2.06 | -80.0% |
| Zach Omen 2.0 | +0.17 | -0.86 | -1.03 | -613.4% |

## 8. Honest interpretation

**Zach's OOS Sharpe (-0.86) is worse than the locked baseline 
(+0.51).** Despite the architectural changes (12:30 filter, tighter 
exits, trailing stop), Zach's parameter set under-performs on the OOS window. 
Possible explanations: (a) tighter target clips winners more than it adds 
win-rate, (b) trailing stop ratchets to breakeven before the trade matures, 
(c) 12:30 filter loses some productive morning entries on this corpus.

**IS→OOS consistency is more important than IS Sharpe alone.** If Zach's IS 
Sharpe is higher but degrades more severely OOS, that's a fitting-to-IS signal, 
not robustness.

## 9. Caveats (mandatory)

- Both models tested on the same consumed 160-session corpus. **In-sample** 
  for both — neither has any forward-test data point.
- Zach's parameters have UNKNOWN provenance with respect to this corpus. They 
  may have been derived from independent analysis (good) or tuned on this same 
  data (bad). Without provenance, OOS Sharpe is not clean validation.
- No forward-test validation exists for either model.
- Per-cell N under Zach's stricter parameters (z=2.0 + 12:30 filter) is smaller 
  than under locked. Individual cell Sharpes are noisier as a result.
- The OMEN-minus-SL hypothesis still hangs on the SHORT_long cell, which is 
  visible in both models. Whether 'minus-SL' is the right exclusion rule, or 
  whether the SHORT_long cell can be fixed structurally, remains open.
- A proper next step would be a pre-registered forward test on 30+ fresh 
  sessions, written BEFORE seeing more of this corpus's behavior. The locked 
  baseline and Zach's variant could both be evaluated against the same fresh 
  data.
