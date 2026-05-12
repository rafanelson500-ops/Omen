# OMEN Side × Gamma Regime Cell Breakdown — Synthesis

**Branch:** `analysis/omen-cell-breakdown-throwaway` (archive only, never merges)
**Source:** IS log (174 trades, 80 sessions, Dec 30 2025 → Apr 21 2026) + OOS log (158 trades, 76 sessions, Sep 8 → Dec 23 2025), concatenated with a `sample` column.
**Status:** Exploratory diagnostic on already-consumed data. No deployment authorization.

---

## 1. Summary table — 4 cells × 2 samples

| cell | sample | n | win% | mean $ | std $ | sum $ | sharpe | max DD $ | mean ATR | exit mix s/t/i/c |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| LONG_long | IS | 44 | 45.5% | +91.16 | 564.65 | +4,011.25 | **+1.541** | −2,768.75 | 2.7548 | s27/t9/i61/c2 |
| LONG_long | OOS | 33 | 57.6% | +74.55 | 378.95 | +2,460.00 | **+2.115** | −998.75 | 3.7148 | s12/t0/i85/c3 |
| LONG_short | IS | 45 | 60.0% | +272.50 | 561.20 | +12,262.50 | **+5.053** | −1,555.00 | 2.9952 | s11/t13/i67/c9 |
| LONG_short | OOS | 29 | 58.6% | +128.41 | 437.91 | +3,723.75 | **+2.067** | −1,553.75 | 3.5187 | s14/t14/i69/c3 |
| SHORT_long | IS | 43 | 46.5% | +159.24 | 591.05 | +6,847.50 | **+3.231** | −1,127.50 | 2.5993 | s26/t14/i58/c2 |
| **SHORT_long** | **OOS** | **48** | **39.6%** | **−86.77** | **594.34** | **−4,165.00** | **−1.953** | −5,987.50 | 4.1268 | s52/t6/i40/c2 |
| SHORT_short | IS | 42 | 42.9% | +36.37 | 553.69 | +1,527.50 | **+0.780** | −4,078.75 | 2.6700 | s33/t10/i52/c5 |
| SHORT_short | OOS | 48 | 45.8% | +44.48 | 472.69 | +2,135.00 | **+1.013** | −1,826.25 | 3.8268 | s19/t6/i71/c4 |

Sharpe formula: `(daily_mean / daily_std) × √252` where `daily_*` are per-trade stats scaled by `trades_per_day = n / n_sessions`.

---

## 2. IS vs OOS deltas per cell (key view)

| cell | IS sharpe | OOS sharpe | Δ sharpe | IS mean $ | OOS mean $ | Δ mean | n IS | n OOS |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| LONG_long | +1.541 | **+2.115** | **+0.574** | +91 | +75 | −16 | 44 | 33 |
| LONG_short | +5.053 | +2.067 | **−2.986** | +273 | +128 | −144 | 45 | 29 |
| **SHORT_long** | **+3.231** | **−1.953** | **−5.184** | +159 | **−87** | **−246** | 43 | 48 |
| SHORT_short | +0.780 | +1.013 | +0.233 | +36 | +44 | +8 | 42 | 48 |

**SHORT_long is the only cell with an OOS Sharpe sign flip.** It went from the second-best cell on IS to the worst on OOS. The other three cells stayed positive on OOS; two improved (LL, SS), one declined but stayed strong (LS).

---

## 3. Statistical tests (Bonferroni N=4)

| cell | OOS n | OOS t vs 0 | p (raw) | p (Bonf×4) | OOS mean 95% boot CI | Welch IS vs OOS t | Welch p |
|---|---:|---:|---:|---:|---|---:|---:|
| LONG_long | 33 | +1.130 | 0.267 | 1.000 | [−48, +205], median +71 | +0.130 | 0.897 |
| LONG_short | 29 | +1.105 | 0.279 | 1.000 | [−97, +349], median +126 | +0.939 | 0.351 |
| SHORT_long | 48 | −1.044 | 0.302 | 1.000 | [−244, +76], median −87 | **+1.989** | **0.0498** |
| SHORT_short | 48 | +0.542 | 0.591 | 1.000 | [−113, +206], median +43 | −0.068 | 0.946 |

**Zero cells reach significance vs zero after Bonferroni.** All four raw p-values ~0.27–0.59 × 4 = clamped at 1.0. Bootstrap mean CIs cross zero in every cell.

**Only SHORT_long shows a meaningful IS-vs-OOS distribution shift** (Welch t=+1.99, p=0.0498 raw — *would* not survive its own Bonferroni correction over 4 cells, but is the only one moving). The IS-vs-OOS Welch results for the other three cells (p=0.35, 0.90, 0.95) are consistent with "same distribution; differences are within trade-level noise on small N."

---

## 4. Regime + side distribution shift (Step 5)

**Gamma regime distribution — NO shift.**

| | IS | OOS |
|---|---:|---:|
| per-trade long-gamma | 50.00% | 51.27% |
| per-trade short-gamma | 50.00% | 48.73% |

Chi-square = 0.0145, p = 0.904 — IS and OOS gamma regime mix is statistically identical.

**Side distribution — material shift, OOS skews short.**

| | IS | OOS |
|---|---:|---:|
| long entries | 51.15% | **39.24%** |
| short entries | 48.85% | **60.76%** |

Chi-square = 4.27, **p = 0.039** — OOS fired short ~62% of the time vs ~49% in-sample. This shift amplifies the damage from SHORT_long because more short entries land in the broken cell.

Per-day majority regime (different definition): IS long-gamma days 45.2%, OOS long-gamma days 38.9%. Slight tilt in distribution-of-trading-days toward short-gamma on OOS but the per-trade regime split is identical, which is what matters for the strategy's exposure.

---

## 5. OMEN-minus-SL view (Step 6)

| view | n | mean $ | sum $ | win% | sharpe | max DD $ |
|---|---:|---:|---:|---:|---:|---:|
| IS full (all 4 cells) | 174 | +141.66 | +24,648.75 | 48.9% | **+5.375** | −2,593.75 |
| IS minus SHORT_long | 131 | +135.89 | +17,801.25 | 49.6% | +4.364 | −2,996.25 |
| OOS full (all 4 cells) | 158 | +26.29 | +4,153.75 | 48.7% | **+1.125** | −4,642.50 |
| **OOS minus SHORT_long** | **110** | **+75.62** | **+8,318.75** | **52.7%** | **+2.787** | **−2,703.75** |

**OOS minus SHORT_long is materially better than full OOS:** Sharpe +2.79 vs +1.13, total P&L roughly doubles, max DD drops 42%, win rate moves from 49% → 53%.

Single-cell views (selection-bias-prone — report with that caveat):

| view | n | sum $ | sharpe |
|---|---:|---:|---:|
| OOS only LONG_long | 33 | +2,460 | +2.115 |
| OOS only LONG_short | 29 | +3,724 | +2.067 |
| OOS only SHORT_long | 48 | **−4,165** | **−1.953** |
| OOS only SHORT_short | 48 | +2,135 | +1.013 |

3 of 4 OOS cells are individually positive. SHORT_long alone accounts for all the loss in the full-strategy P&L.

---

## 6. Time-of-day per positive-OOS-Sharpe cell (Step 7, exploratory)

**LONG_long OOS (sharpe +2.115):** carried by 14:30–15:29 bucket (n=23, +$860) plus a few earlier wins. 56.5% win rate in the carrying bucket.

**LONG_short OOS (sharpe +2.067):** opening drive 09:30–10:29 (n=7, +$1,909, win 71%) and 12:30–13:29 (n=4, +$1,530, win 50%) carry; 14:30–15:29 bucket is *negative* (n=14, −$358). Pattern reverses across the day.

**SHORT_short OOS (sharpe +1.013):** 14:30–15:29 (n=28, +$1,691) and 15:30–15:55 (n=3, +$1,391, win 67%) carry; morning is negative (09:30–10:29, n=11, −$399).

Hour buckets 10:30–12:29 are empty for all cells per OMEN's lunch blackout (no entries 10:30–12:30 ET).

These TOD patterns are exploratory color — sample sizes per (cell × hour bucket) are tiny, none survive even informal multiple-comparison.

---

## 7. Pattern verdict — MIX of (A) and (D)

The four options laid out in the spec:
- **A — Only SL is broken; other three cells survived OOS** ✓ partially
- B — SL is worst but all four cells degraded materially ✗ — three cells held or improved
- C — One specific cell carries the strategy; others are noise ✗ — three cells contribute meaningfully
- **D — Regime distribution shift explains the degradation** ✓ partially (side mix, not gamma regime)
- E — Some mix of the above — **yes, A and D combined**

**Best characterization:**
1. SHORT_long is the **uniquely broken cell** — only cell with an OOS Sharpe sign flip; only cell with a Welch IS-vs-OOS shift at raw p<0.05. The IS-period SL stats (+$159 mean, +3.23 Sharpe) were not a robust property of the strategy.
2. The other three cells **held qualitatively but degraded statistically** — none reach Bonferroni significance vs zero on OOS, but Sharpe directions are intact (LL +2.12, LS +2.07, SS +1.01) and Welch tests find no IS-vs-OOS distribution change.
3. **Side distribution shifted** — OOS fired 61% short vs IS 49% (chi-square p=0.039). This amplifies SL's damage. Gamma regime distribution is unchanged.

The cell-level picture is therefore: **one cell broke, OMEN happened to over-fire on that cell in OOS, the other three cells were okay**. But "okay" here means "Sharpe direction preserved, no Bonferroni-significant edge." That's not the same as "cells confirmed to have edge."

---

## 8. Candidate flagging (per pre-reg gate)

Pre-reg gate: OOS Sharpe > 1.5 **AND** N ≥ 30 **AND** Bonferroni p < 0.05.

| cell | OOS sharpe (need >1.5) | OOS N (need ≥30) | Bonf p (need <0.05) | candidate? |
|---|---:|---:|---:|---|
| LONG_long | **+2.115** ✓ | **33** ✓ | 1.000 ✗ | no |
| LONG_short | **+2.067** ✓ | 29 ✗ | 1.000 ✗ | no |
| SHORT_long | −1.953 ✗ | 48 ✓ | 1.000 ✗ | no |
| SHORT_short | +1.013 ✗ | 48 ✓ | 1.000 ✗ | no |

**Zero cells flagged as candidate.** The Bonferroni gate kills every cell — none has a raw p-value tight enough to clear ×4 correction.

LONG_long comes closest: it passes the Sharpe and N gates and fails only on the significance gate. Its raw p=0.267 → Bonferroni p=1.000.

---

## 9. Caveats

- **All findings are on consumed data.** The IS-vs-OOS Welch test for SHORT_long (p=0.0498) doesn't survive its own multi-cell correction. The "OOS minus SL improves Sharpe to +2.79" finding is post-hoc cell selection — exactly the structure of curve-fitting.
- **Sample sizes per cell are small** (29–48 trades per OOS cell). Sharpe estimates with N<50 are highly variable; bootstrap CIs on the OOS means cross zero in every cell.
- **No surviving cell.** No cell passes the pre-registered candidate gate. The closest is LONG_long (passes Sharpe and N, fails significance).
- **Side distribution shift is real (p=0.039 raw, would survive Bonferroni at N=2 cells: side & regime).** But chi-square at this magnitude on 174+158 trades is still within plausible variance of trading-strategy behavior — the underlying signal generator (FlowBurst on gexoflow_z + dexoflow_z) doesn't have an explicit symmetry constraint, so a mild side-mix drift between samples is not surprising in itself.
- **OMEN-minus-SL Sharpe boost (1.13 → 2.79)** is the largest cell-level finding, but it's the most selection-bias-prone view in this analysis. Removing the worst-performing OOS cell on the basis of its OOS performance is the textbook overfitting move. A real defense requires identifying SL as broken before observing its OOS performance — which is not the situation here.
- **No deployment of any cell-level subset is authorized by this analysis.** Per project discipline, any cell-level filter would require fresh forward-test data to validate.

---

## 10. Recommended next step (descriptive, per the four-option list)

Per spec Step 10 verdict mapping for mixed pattern:

- **Pattern A component** (SHORT_long is the broken cell): if pursued, a 3-cell version of OMEN (excluding SHORT_long) would need fresh-forward-data validation. The OMEN-minus-SL Sharpe of +2.79 on OOS-as-seen is too contaminated by hindsight to act on.
- **Pattern D component** (side-mix shift): the 61% short bias on OOS vs 49% on IS suggests OMEN's signal generator responded differently to the regime change between samples. The OMEN signal logic does NOT include an explicit side-balancing mechanism — the side comes from `dexoflow_z` sign and `gexoflow_z` magnitude jointly. A future analysis could look at whether the OOS period's gexoflow_z / dexoflow_z signs themselves were distribution-shifted; that would be a feature-side rather than strategy-side question.

The user decides what (if anything) to do with these patterns. This synthesis does not propose strategy changes; it identifies the patterns.

---

## 11. Disclaimer

Throwaway branch, archive only. The locked OMEN config is unchanged. The TRCB-v1 FAIL verdict and the OOS Tier 1 + Tier 2 results from prior work are unchanged. This is exploratory color on already-burned data.

**Protected paths untouched:** `cheese/`, `strategy.py`, `backtest.py`, `market.py`, `gex.py`, `features.py`, locked config.
