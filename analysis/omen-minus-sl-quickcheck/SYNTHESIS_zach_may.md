# OMEN — Zach May parameter comparison (THROWAWAY)

Branch: `analysis/omen-minus-sl-quickcheck-throwaway` (throwaway / archive only; never merges to main).
Generated: 2026-05-12T21:14:13

## 1. Disclosure

## DISCLOSURE — provenance unknown, sample meaningless

This script applies an alternative parameter set sourced from a third-party
spreadsheet (Zach's monthly params) to the same 8-9 fresh OMEN sessions
used in the OMEN-minus-SL quick-check.

Provenance of alternative parameters: UNKNOWN. The user has not verified
whether these parameters come from a pre-registered adaptive framework,
mechanistic derivation, or monthly performance tuning. Without provenance,
any result here is uninterpretable as evidence about which parameter set
"works better."

Sample size: ~18 trades. Statistically meaningless for parameter comparison.

This test does NOT authorize switching the OMEN locked baseline. The user
has acknowledged that no parameter change will be made based on this result.


## 2. Parameter sets compared

| param | locked-14 (orig quick-check) | locked-20 (ATR sensitivity) | Zach May |
|---|---|---|---|
| z_threshold | 1.8 | 1.8 | **2.0** |
| stop_atr_mult | 2.0 | 2.0 | 2.0 |
| target_atr_mult | 4.5 | 4.5 | **5.0** |
| time_stop_min | 25 | 25 | **35** |
| atr_window_bars | 14 | **20** | 14 |
| blackout_lunch | True | True | True |
| bar_freq | 5min | 5min | 5min |

Sessions analyzed: **8** (2026-04-30 → 2026-05-11; same set across all three runs).

## 3. Three-way side-by-side comparison

| metric | locked (ATR=14) | locked (ATR=20) | Zach May |
|---|---:|---:|---:|
| N total trades | 18 | 18 | 14 |
| Cell counts (LL/LS/SL/SS) | 2/6/1/9 | 2/6/1/9 | 2/5/0/7 |
| Full OMEN win rate | 61.1% | 61.1% | 50.0% |
| Full OMEN mean $ | $+4.72 | $+34.58 | $+63.30 |
| Full OMEN sum $ | $+85 | $+622 | $+886 |
| Full OMEN Sharpe | +0.30 | +2.27 | +3.27 |
| Full OMEN max DD | $-1251 | $-1026 | $-1212 |
| Minus-SL N | 17 | 17 | 14 |
| Minus-SL win rate | 64.7% | 64.7% | 50.0% |
| Minus-SL sum $ | $+509 | $+1059 | $+886 |
| Minus-SL Sharpe | +1.84 | +4.07 | +3.27 |

## 4. Trade-level overlay — locked-14 vs Zach May

FlowBurst entries depend on `gexoflow_z` ≥ z_threshold. Zach uses 2.0 vs 
locked 1.8, so Zach should produce a *subset* of locked-14's entries plus 
potential mismatches near the threshold. Exit reasons and PnL change due 
to the wider target (5.0×ATR) and longer time stop (35min vs 25min).

- Trades present in **both** (matched on entry_time + side + gamma_regime): **14**
- Trades only in locked-14: **4** (filtered out by z_threshold=2.0)
- Trades only in Zach May: **0** (unexpected if Zach is a strict subset — investigate if non-zero)

- Among the 14 matched trades, **13** have the same `exit_reason` under both parameter sets; **1** change exit reason (typically locked time → Zach target, or locked time → Zach time).

### Exit-reason distribution per parameter set

| param set | time | stop | target | session_close |
|---|---:|---:|---:|---:|
| locked-14 | 11 | 6 | 1 | 0 |
| locked-20 | 13 | 4 | 1 | 0 |
| Zach May | 11 | 3 | 0 | 0 |

## 5. Per-cell breakdown — Zach May params

| cell | N | mean $ | sum $ |
|---|---:|---:|---:|
| LONG_long | 2 | $+445.00 | $+890 |
| LONG_short | 5 | $+137.50 | $+688 |
| SHORT_long | 0 | $+0.00 | $+0 |
| SHORT_short | 7 | $-98.75 | $-691 |

**Notable: Zach's params produced ZERO `SHORT_long` trades on this window.** 
That means the OMEN-minus-SL exclusion is **vacuous** under Zach's params on 
this sample — there's nothing to exclude — so the minus-SL Sharpe equals the 
full Sharpe by construction. The original quick-check's directional finding 
(minus-SL > full) cannot be tested under these params on these sessions.

## 6. Honest interpretation

**Trade count changed substantially.** Locked z=1.8 → 18 trades, Zach z=2.0 → 14 trades on the same 8 sessions. The higher z_threshold filters out ~4 signals, all of which would have fired under locked-14.

**Direct Sharpe comparison is contaminated.** Three different parameter sets 
on the same 8-session sample is exactly the kind of multiple-comparison setup 
that produces false 'winners' from noise. With ~14-18 trades per arm, any 
ranking we observe could easily flip on the next 8 sessions.

**Zach's full Sharpe (+3.27) is higher than 
locked-14's (+0.30).** That's a data point, not a verdict. 
Possible explanations include: (a) the wider target/longer time-stop happened 
to capture moves that locked-14's tighter exits clipped, (b) the higher 
z_threshold happened to filter out a couple of losing trades on these 
sessions, (c) coincidence. At n=14-18, distinguishing between these is 
statistically impossible.

**The OMEN-minus-SL diagnostic is uninformative under Zach's params here** 
because the SHORT_long cell didn't fire at all. The original quick-check's 
hypothesis (minus-SL improves Sharpe) **can't be tested** in the Zach arm.

**What this result tells us about which parameter set is 'better':** 
**almost nothing.** Both are running on 18 and 14 trades respectively over 8 
sessions. Any conclusion needs (a) provenance for Zach's params, (b) ≥30 
fresh sessions, (c) a pre-registered test that locked the comparison BEFORE 
seeing this data. None of those conditions are met.

## 7. Caveats (mandatory)

- **18 / 14 trades is too small for any verdict.** Period.
- **Provenance of Zach's params is unknown.** They could be mechanistically 
  derived, pre-registered, monthly tuned, or random — we don't know. Without 
  provenance, any positive read is uninterpretable as evidence of edge.
- **Same 8 fresh sessions used for a third analysis.** This data pool is now 
  more consumed than it was at the start of the quick-check. Future fresh-
  data work that touches Apr 30 → May 11 will need to account for the multiple 
  parameter-set looks on this window.
- **No deployment, no baseline switch, no claim of 'Zach's params are better' 
  based on this result.** Hard rule, applies regardless of the numbers above.
- **Zach's trade count (14) is within the noise-dominated range** 
  for Sharpe estimation. Standard error on the Sharpe estimate is enormous.
