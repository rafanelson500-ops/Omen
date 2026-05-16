# Morning & Noon-Transition Churn-IC Extraction
_generated: 2026-05-16T00:28:49-05:00_

> **HEADER NOTE.** The task mandated a verbatim header whose text was truncated in the request and never supplied. The block below is reconstructed from the task's explicit scope guards; replace with the verbatim text when provided (one-line edit, numbers unaffected).

## Header

- **Purpose:** cross-project consultation extraction for the OMEN+V4.1 synthesis project; resolves a conditional bookmark on their side. Exploratory.
- **DSR accounting:** counts as **one additional trial** in OMEN's multiple-comparison search on the churn signal. Recorded here for FUTURE DSR accounting; the DSR ledger is **not** modified by this extraction.
- **Scope guard:** NOT a re-opening of Step 3; NOT a re-ranking input for OMEN's post-verdict pre-reg shortlist (churn currently #2 — unchanged regardless of this result); NOT a modification of any locked baseline parameter.
- **Branch:** `analysis/churn-morning-bucket-throwaway` (archive-only; never merges to main; cheese/ untouched).
- **Methodology source:** `OneMinL2/scripts/signal_ic/churn_conditional.py` (mirrored exactly; constants cite file:line in the script header).

## Step 1 — methodology (mirrored exactly)

1-min corpus; feature `churn_lag1`=churn.shift(1) per session; target `next_return`=log(next_close/close) per session (signed) and `abs_return`=|next_return| (magnitude); frame drops null next_return/churn_lag1; per-session **Spearman** IC (skip <30 bars/session or constant series); cross-session one-sample t = mean/(std_ddof1/√n), two-tailed p. Buckets from `ts_open.dt.time` (corpus tz = America/New_York → ET), inclusive-lower / exclusive-upper.

## Step 2 — corpus

- pre-IS = `date < 2025-12-26`
- **sessions: 75** (2025-09-08 → 2025-12-24); bars: **29,100**
- expected 75 sessions Sep 8 2025 – Dec 24 2025 — **matches, no change**

## Methodology-fidelity gate (re-derived Step 3 §3, signed)

| bucket (ET) | n bars | mean PS IC | t (mine) | t (reported) | match | n sess |
|---|---:|---:|---:|---:|:--:|---:|
| open [09:30,10:30) | 4,425 | +0.04085 | +3.161 | +3.161 | OK | 75 |
| mid_morning [10:30,12:00) | 6,750 | +0.04470 | +3.591 | +3.591 | OK | 75 |
| lunch [12:00,14:00) | 9,000 | +0.04894 | +5.033 | +5.033 | OK | 75 |
| afternoon [14:00,16:00) | 8,925 | +0.01779 | +1.501 | +1.501 | OK | 73 |

> Gate **PASSED** — re-derivation reproduces the reported §3 signed t-stats within ±0.01, so the slices below are directly comparable to the published lunch +5.033 / afternoon +1.501 (signed) numbers.

## Step 3 — new slices (both targets, side by side)

**Signed `next_return`** (directly comparable to §3 lunch +5.033, afternoon +1.501, mid_morning +3.591, open +3.161):

| slice (ET) | n bars | global ρ | global p | mean PS IC | median | t-stat | t p | % sess>0 | n sess |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| morning [09:30,11:30) | 8,925 | +0.01052 | 3.205e-01 | +0.04150 | +0.03384 | +4.521 | 2.297e-05 | 66.7% | 75 |
| noon_transition [11:30,12:00) | 2,250 | +0.03140 | 1.365e-01 | +0.03502 | +0.03404 | +1.652 | 1.027e-01 | 56.0% | 75 |
| _whole-corpus (signed, §5 anchor)_ | 29,100 | — | — | +0.02751 | +0.03234 | +4.044 | 1.277e-04 | 69.3% | 75 |

**Magnitude `|next_return|`** (comparable to the §5 whole-corpus magnitude row only — Step 3 published **no** per-time-of-day |return| baseline):

| slice (ET) | n bars | global ρ | global p | mean PS IC | median | t-stat | t p | % sess>0 | n sess |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| morning [09:30,11:30) | 8,925 | +0.38499 | 0.000e+00 | +0.17679 | +0.17440 | +11.756 | 1.344e-18 | 93.3% | 75 |
| noon_transition [11:30,12:00) | 2,250 | +0.46588 | 1.311e-121 | +0.03100 | +0.04427 | +1.447 | 1.520e-01 | 56.0% | 75 |
| _whole-corpus (\|return\|, §5 anchor)_ | 29,100 | — | — | +0.28172 | +0.29082 | +17.350 | 8.581e-28 | 100.0% | 75 |

### Per-slice observation sanity

- **morning** [09:30,11:30): sessions in slice 75, min obs/session **119**, median **119**; sessions with <30 obs: none
- **noon_transition** [11:30,12:00): sessions in slice 75, min obs/session **30**, median **30**; sessions with <30 obs: none

## Step 4 — reconciliation of reported lunch/afternoon

From `churn_conditional.py:31-36` and `diagnostics/signal_ic/03_churn_conditional.md §3`:

- Reported **lunch t=5.033** covers **[12:00, 14:00) ET** (mean PS IC +0.04894, 75 sess) — *not* 12:00-13:00, *not* 11:30-13:00.
- Reported **afternoon t=1.501** = **[14:00, 16:00) ET** (73 sess).
- Step 3 buckets tile **[09:30, 16:00) with no gap** (open/mid_morning/lunch/afternoon; script asserts 0 unbucketed).
- **Noon-transition [11:30, 12:00) is a strict sub-slice of Step 3's `mid_morning` [10:30, 12:00)** (reported t=+3.591). It was **never uncategorized** and **never in lunch** — the suspected gap does not exist.
- **Morning [09:30, 11:30)** = all of Step 3 `open` [09:30,10:30) (t=+3.161) **plus** the first hour of `mid_morning` [10:30,11:30); it is a recombination across two existing §3 buckets, not new uncategorized data.

_End of report. Numbers + reconciliation only — no interpretation, no ranking input, no parameter change._
