# Intraday momentum mechanism investigation (THROWAWAY)

Branch: `analysis/intraday-momentum-exploratory-throwaway` (throwaway / archive only; never merges to main).
Generated: 2026-05-13T10:42:46

## 1. Disclosure

## DISCLOSURE — cumulatively biased corpus, cannot validate

This analysis runs on the 160-session corpus used for multiple prior
analyses (TRCB-v1/v2, Q1-Q9 diagnostics, cell-breakdown, all bug-fix
re-runs, microprice continuation, GEX permutation re-run, mechanism
hypotheses). The data is cumulatively biased from approximately 15
prior investigations.

Results here cannot validate any new hypothesis. They can only filter
whether intraday momentum is worth pre-registering as a hypothesis for
fresh-data forward testing after the OMEN-minus-SL verdict (pre-reg
9c1c22f).

No deployment authorization. No parameter modification. No pre-reg
change. No baseline modification.


## 2. Setup

Following Baltussen, Da & Soebhag (2021) and related intraday-momentum literature. Windows on each RTH session:
- **Morning**: 09:30 - 12:00 ET (open → midday close)
- **Midday**:  12:00 - 14:30 ET
- **Last hour**: 15:00 - 16:00 ET (final hour close)
- **Full session**: 09:30 - 16:00 ET

Corpus: 160 sessions with full-window 1s ES data ({'IS': 74, 'OOS': 72, 'OTHER': 14}).

## 3. Regression results

R1: `last_hour_ret = α + β · morning_ret + ε`  (does last hour follow morning?)
R2: `last_hour_ret = α + β · (morning_ret + midday_ret) + ε`  (does last hour follow cumulative AM through 14:30?)

| sample | regression | N | α (bp) | β | β t-stat | R² | p-value |
|---|---|---:|---:|---:|---:|---:|---:|
| FULL | R1 | 160 | -0.94 | +0.0582 | +1.53 | 0.0146 | 0.1283 |
| FULL | R2 | 160 | -0.89 | +0.0285 | +0.90 | 0.0051 | 0.3712 |
| IS | R1 | 74 | +1.76 | +0.0255 | +0.40 | 0.0022 | 0.6938 |
| IS | R2 | 74 | +1.73 | +0.0321 | +0.59 | 0.0049 | 0.5542 |
| OOS | R1 | 72 | -4.17 | +0.0805 | +1.72 | 0.0406 | 0.0897 |
| OOS | R2 | 72 | -4.40 | +0.0233 | +0.59 | 0.0050 | 0.5541 |

### Reading the regressions

- Full-corpus R1: β = +0.0582, t = +1.53, p = 0.1283. NO significant relationship at α=0.05.
- Full-corpus R2: β = +0.0285, t = +0.90, p = 0.3712. NO significant relationship at α=0.05.

## 4. Conditional momentum buckets

Split sessions by morning return:
- **big up** : morning_ret > +0.5% (~+0.50 sigma in equity-index intraday)
- **flat**   : |morning_ret| ≤ 0.5%
- **big down**: morning_ret < −0.5%

| sample | bucket | N | mean last_hr ret (bp) | t vs zero |
|---|---|---:|---:|---:|
| FULL | big_up | 23 | -6.97 | -1.45 |
| FULL | flat | 116 | +1.75 | +0.80 |
| FULL | big_down | 21 | -8.30 | -1.13 |
| IS | big_up | 16 | +1.62 | +0.33 |
| IS | flat | 47 | +1.83 | +0.39 |
| IS | big_down | 11 | +2.66 | +0.28 |
| OOS | big_up | 7 | -26.63 | -3.78 |
| OOS | flat | 55 | +1.30 | +0.58 |
| OOS | big_down | 10 | -20.35 | -1.96 |

## 5. OMEN signal alignment with morning-return regime

Cross-tab of OMEN trades by entry-window × morning_ret direction. AM+ / AM− / AM0 are sessions where morning_ret > 0 / < 0 / == 0 (== 0 is a near-empty sentinel; sessions with morning_ret exactly 0 are rare).

| window | AM+ (n / mean $ / sum $) | AM− | AM0 |
|---|---|---|---|
| morning | n=37  mean $+45.84  sum $+1696 | n=39  mean $+65.35  sum $+2549 | (n=0) |
| midday | n=145  mean $+58.88  sum $+8538 | n=107  mean $-25.62  sum $-2741 | n=3  mean $+70.00  sum $+210 |
| early_pm | n=39  mean $-17.18  sum $-670 | n=31  mean $-21.53  sum $-668 | n=1  mean $-255.00  sum $-255 |
| last_hour | n=55  mean $+46.93  sum $+2581 | n=47  mean $+62.69  sum $+2946 | (n=0) |

## 6. Simple control strategy: long/short ES at 14:30 by cumulative-AM sign

Entry at 14:30 ET close. Direction: long if `morning_ret + midday_ret > 0`, 
short if < 0. Exit at 15:55 ET close. Cost model matches the locked OMEN CostModel ($17.50 round-trip = $2.50 commission/side + 0.5-tick slippage/side).

Note on spec: the prompt's parenthetical ('1 tick slippage per side, $5 
commissions') doesn't match the actual locked OMEN CostModel; I used OMEN's 
actual numbers ($17.50 RT) to keep the comparison apples-to-apples with OMEN's 
recorded trade costs.

| arm | N | win | mean $ | sum $ | Sharpe (ann.) | max DD |
|---|---:|---:|---:|---:|---:|---:|
| Control FULL | 160 | 45.6% | $+10.23 | $+1638 | +0.19 | $-14122 |
| Control IS | 74 | 52.7% | $+84.02 | $+6218 | +1.42 | $-7630 |
| Control OOS | 72 | 38.9% | $-82.08 | $-5910 | -1.49 | $-8900 |

**OMEN reference (bugfixed)**:
- IS Sharpe (annualized) = **+2.57** (257 trades)
- OOS Sharpe (annualized) = **+0.51** (247 trades)

### Control vs OMEN — head-to-head

- OOS Sharpe: control -1.49 vs OMEN +0.51
  → OMEN beats control by > 0.5 Sharpe on OOS

## 7. Filter outcome (per spec criteria A-E)

**Outcome D**: intraday momentum is NOT statistically present in this corpus at the conventional α=0.05 threshold. The literature mechanism does not manifest here. Combined with Tier 5.3's bugfixed GEX permutation p=0.27, the broader 'gamma-hedging-drives-trend' mechanism appears weaker than the OMEN strategy's framing assumes.

### Inputs to the filter

- R1 full-corpus β t-stat: +1.53 (threshold ±2.0)
- R2 full-corpus β t-stat: +0.90
- Control OOS Sharpe: -1.49 vs OMEN OOS +0.51

## 8. Caveats (mandatory)

- **Consumed-corpus analysis.** ~15 prior investigations have read this corpus.
- **Literature parameters used, no tuning** (windows = 09:30/12:00/14:30/15:00/16:00).
- **No new pre-reg**, no parameter change authorized.
- **Results inform whether to bookmark for fresh-data pre-reg only.**
- **The control strategy's cost model** matches locked OMEN ($17.50 RT), not the 
  prompt's parenthetical ($35 RT). The Sharpe gap is robust to that detail at 
  the per-session sample size here.
- **OOS sample for the control is 72 sessions**, IS is 74 sessions. Both are 
  modest. A Sharpe gap of < 0.5 between control and OMEN at this n is well within 
  the noise floor.
- **'AM±' cross-tab** in Section 5 is descriptive only; sample sizes per cell are 
  small (typically < 50) and the directional Sharpe pattern is not a verdict.
