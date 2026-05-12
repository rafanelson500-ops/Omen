# TRCB-v2 Phase 3 — OMEN Trade Filter (IN-SAMPLE, THROWAWAY)

## CRITICAL METHODOLOGICAL DISCLOSURE

This test is NOT a valid pre-registration. The user is running TRCB-v2
on the same 160-session corpus that:
  - TRCB-v1 Phase 2 already consumed
  - Q1/Q2/Q3 post-mortem already analyzed at multiple window lengths
  - Q4 MFE/MAE analysis already consumed
  - Q2 specifically tested the 30s window and showed positive signal

The TRCB-v2 parameters (30s window, 1.5:1 ratio) were chosen AFTER
observing post-mortem results that showed 30s windows produce positive
forward signal. This means the parameter selection was informed by the
data being tested. This is in-sample parameter tuning by definition,
regardless of any pre-registration documentation.

A positive result here does NOT constitute validation of TRCB-v2. It
constitutes evidence that the parameters that already looked good on
this data continue to look good on this data. To validate TRCB-v2, fresh
forward-only sessions must be used in a future test.

A negative result here would be more informative than a positive one —
it would indicate the framework is weaker than the post-mortem suggested.

The user has explicitly overridden methodological objections and is
proceeding with this test knowing the above.


**Generated:** 2026-05-12T18:11:40
**Branch:** `analysis/trcb-v2-consumed-data-test-throwaway`

## Setup

- Trades: 332 (IS=174, OOS=158)
- Filter params: WINDOW=30s, VOL_MULT=1.0, DELTA_RATIO=1.5, PRICE_ATR=0.25, ATR=14
- P4 uses `atr_at_entry` directly from the trade log (OMEN's SMA(14) ATR), not the Phase-2 Wilder ATR.
- P2 baseline uses trailing-100-bar median of 30s directional volume from per_bar_volumes_30s.
- `FILTER_CONFIRMED` = trade's direction matches a v2 trigger at T.

## Filter-pass counts
- Total trades              : **332**
- Evaluable                 : 254
- FILTER_CONFIRMED          : **7** (2.1% of total)
- IS confirmed              : 6 / 174
- OOS confirmed             : 1 / 158

## Performance table — both arms × IS/OOS/Combined × all/confirmed/rejected

| arm | sample | subset | N | win | mean | sum | Sharpe | max DD |
|---|---|---|---:|---:|---:|---:|---:|---:|
| full_omen | IS | all | 174 | 48.9% | $+141.66 | $+24649 | +5.38 | $-2594 |
| full_omen | IS | confirmed | 6 | 50.0% | $+239.79 | $+1439 | +1.98 | $-392 |
| full_omen | IS | rejected | 168 | 48.8% | $+138.15 | $+23210 | +5.12 | $-2594 |
| full_omen | OOS | all | 158 | 48.7% | $+26.29 | $+4154 | +1.13 | $-4642 |
| full_omen | OOS | confirmed | 1 | 100.0% | $+7.50 | $+8 | — | $+0 |
| full_omen | OOS | rejected | 157 | 48.4% | $+26.41 | $+4146 | +1.12 | $-4642 |
| full_omen | Combined | all | 332 | 48.8% | $+86.75 | $+28802 | +3.45 | $-4642 |
| full_omen | Combined | confirmed | 7 | 57.1% | $+206.61 | $+1446 | +1.41 | $-392 |
| full_omen | Combined | rejected | 325 | 48.6% | $+84.17 | $+27356 | +3.30 | $-4642 |
| omen_minus_sl | IS | all | 131 | 49.6% | $+135.89 | $+17801 | +4.49 | $-2996 |
| omen_minus_sl | IS | confirmed | 6 | 50.0% | $+239.79 | $+1439 | +2.03 | $-392 |
| omen_minus_sl | IS | rejected | 125 | 49.6% | $+130.90 | $+16362 | +4.18 | $-2996 |
| omen_minus_sl | OOS | all | 110 | 52.7% | $+75.62 | $+8319 | +3.03 | $-2704 |
| omen_minus_sl | OOS | confirmed | 1 | 100.0% | $+7.50 | $+8 | — | $+0 |
| omen_minus_sl | OOS | rejected | 109 | 52.3% | $+76.25 | $+8311 | +3.02 | $-2704 |
| omen_minus_sl | Combined | all | 241 | 51.0% | $+108.38 | $+26120 | +3.87 | $-2996 |
| omen_minus_sl | Combined | confirmed | 7 | 57.1% | $+206.61 | $+1446 | +1.49 | $-392 |
| omen_minus_sl | Combined | rejected | 234 | 50.9% | $+105.44 | $+24674 | +3.69 | $-2996 |

## Read-with-caution notes

- See CRITICAL DISCLOSURE above. **In-sample.** Positive findings do not validate the framework.
- `omen_minus_sl` excludes the `SHORT_long` cell, the worst-performing OOS cell in the prior cell-breakdown analysis (also throwaway, also in-sample selection).
- A meaningful read: comparing **confirmed vs rejected** Sharpe *within a single arm × sample*. If FILTER_CONFIRMED trades systematically outperform FILTER_REJECTED on the same data, that's consistent with v2 measuring something — but cannot distinguish 'real edge' from 'curve-fit to this data'.
- Small subset sizes (especially OOS confirmed) make Sharpe estimates noisy.
