# Q9 — GEX mechanism diagnostic (THROWAWAY)

Branch: `analysis/gex-mechanism-diagnostic-throwaway` (throwaway / archive only; never merges to main).
Generated: 2026-05-13T00:10:28

## 1. Disclosure

## DISCLOSURE — descriptive only, no statistical claims

This diagnostic runs on the 160-session corpus that has been used for
multiple prior analyses. Findings are descriptive only — they
characterize where OMEN's signals fire in GEX feature space, not
whether GEX features have predictive edge. The Tier 5.3 permutation
test already addressed the predictive-edge question (p=0.14, cannot
reject null).


## 2. Population feature distributions

Evaluable population: **8,852** RTH 5-min bars across the 160-session corpus where both `gexoflow_z` and `dexoflow_z` are finite (post-warmup, both rolling z-scores populated).

### gexoflow_z and dexoflow_z quantiles

| q | gexoflow_z (population) | gexoflow_z (OMEN signals) | dexoflow_z (population) | dexoflow_z (OMEN signals) |
|---:|---:|---:|---:|---:|
| 0.01 | -4.407 | -4.949 | -2.689 | -3.579 |
| 0.05 | -2.399 | -3.761 | -1.485 | -2.188 |
| 0.10 | -1.723 | -3.136 | -1.058 | -1.698 |
| 0.25 | -0.827 | -2.444 | -0.468 | -0.842 |
| 0.50 | -0.027 | -1.812 | +0.058 | -0.016 |
| 0.75 | +0.817 | +2.430 | +0.542 | +0.810 |
| 0.90 | +1.706 | +3.195 | +1.113 | +1.582 |
| 0.95 | +2.337 | +3.638 | +1.520 | +2.002 |
| 0.99 | +4.118 | +5.387 | +2.729 | +3.938 |

Population |gexoflow_z| percentile reference: 90=2.363, 95=3.095, 99=5.355. Population fraction with |gexoflow_z| ≥ 1.8: **18.21%**.

Sanity: **100.0%** of OMEN-signal bars have |gex_z| ≥ 1.8 as expected (FlowBurst threshold).

## 3. OMEN signal locations within the population distribution

OMEN's z=1.8 threshold sits roughly at the **81.8-th percentile** of |gexoflow_z|. The signal set is the right tail of the 
two-sided distribution. Within that tail:

- **|gex_z| ∈ [1.8, 2.0)**: n=87
- **|gex_z| ∈ [2.0, 2.5)**: n=148
- **|gex_z| ∈ [2.5, 3.0)**: n=91
- **|gex_z| ∈ [3.0, ∞)**: n=102

Roughly **20.3%** of OMEN signals fall in the [1.8, 2.0) bucket — the bin immediately above the threshold. Signals are concentrated near the 
threshold rather than at extreme z values.

## 4. Direction-conditional analysis

- **LONG signals** (n=211): mean gex_z = +2.652, median = +2.451; mean dex_z = +1.064, median = +0.816.
- **SHORT signals** (n=217): mean gex_z = -2.654, median = -2.443; mean dex_z = -1.065, median = -0.821.

OMEN's strategy is symmetric by construction (long requires gex_z > +1.8 AND dex_z > 0; short requires gex_z < −1.8 AND dex_z < 0). The signs above 
confirm that. The magnitudes are approximately mirrored.

### Winners vs losers (|gex_z| within each direction)

| subset | N | |gex_z| mean | |gex_z| median | net mean $ |
|---|---:|---:|---:|---:|
| long winners | 103 | 2.656 | 2.471 | $+383.47 |
| long losers | 108 | 2.649 | 2.388 | $-291.57 |
| short winners | 103 | 2.685 | 2.454 | $+354.65 |
| short losers | 114 | 2.625 | 2.396 | $-303.46 |

Long winners' |gex_z| − losers': **+0.006**. 
Short winners' |gex_z| − losers': **+0.061**.
Differences are small (<0.1) in both directions: winners and losers fire at 
nearly identical z-magnitudes. The z-magnitude does not separate winners from 
losers within either direction.

## 5. Z-magnitude buckets vs forward P&L

| |gex_z| bucket | N | sessions | win rate | mean $ | sum $ | Sharpe |
|---|---:|---:|---:|---:|---:|---:|
| [1.8, 2.0) | 87 | 68 | 39.1% | $-56.58 | $-4922 | -2.75 |
| [2.0, 2.5) | 148 | 95 | 51.4% | $+26.00 | $+3848 | +1.24 |
| [2.5, 3.0) | 91 | 64 | 46.2% | $+13.96 | $+1270 | +0.61 |
| [3.0, ∞) | 102 | 73 | 52.9% | $+95.55 | $+9746 | +3.05 |

Mean P&L per trade is **non-monotonic** across z-magnitude buckets. 
BUT the endpoints differ sharply: the lowest-z bucket **[1.8, 2.0)** has mean = **$-56.58** (Sharpe **-2.75**), 
while the highest-z bucket **[3.0, ∞)** has mean = **$+95.55** (Sharpe **+3.05**). Spread between extremes = **$+152.13/trade**.

**The threshold-clearing bucket [1.8, 2.0) is net-negative** (87 trades, sum=$-4922). Signals that 
just cleared the z=1.8 cut on the consumed corpus lost money on average. 
The extreme-tail bucket is responsible for most of the strategy's 
realized P&L.

Interpretation is mixed:
- Endpoints are very different ($+152/trade spread), which is 
  inconsistent with z being a pure binary 'above threshold' label.
- Middle buckets are not ordered (2.5-3.0 is worse than 2.0-2.5), which 
  is inconsistent with z being a clean gradient mechanism variable.
- Combined: z carries SOME magnitude information at the extremes, but not 
  enough to produce a clean linear gradient. The most natural reading is 
  that there are two regimes — 'just barely a signal' (worst returns) and 
  'extreme dealer hedging event' (best returns) — with a noisy middle.

## 6. Volatility overlap

Top-5% realized-volatility threshold (5-bar pct-return std): **0.00131**. Population top-vol bars: **443**.

- OMEN signals also in top-5% realized vol: **36 / 428** (8.4%)
- Top-vol bars that are NOT OMEN signals: **407 / 443** (91.9%)

### realized_vol distribution (population vs OMEN signals)

| q | population (×1e-4) | OMEN signals (×1e-4) |
|---:|---:|---:|
| 0.01 | 0.90 | 0.97 |
| 0.05 | 1.49 | 1.73 |
| 0.10 | 1.88 | 2.02 |
| 0.25 | 2.82 | 3.14 |
| 0.50 | 4.57 | 4.89 |
| 0.75 | 7.16 | 7.76 |
| 0.90 | 10.53 | 11.90 |
| 0.95 | 13.10 | 15.70 |
| 0.99 | 19.46 | 24.80 |

OMEN-signal median realized_vol / population median: **1.07×**.
Less than 25% of OMEN signals overlap with the top-5% vol bars. OMEN's 
signal set is distinct from a simple realized-volatility selector.

## 7. Honest interpretation

This diagnostic cannot validate or invalidate GEX as a mechanism. What it 
characterizes:

- **Signal location**: OMEN's z=1.8 threshold puts the signal set in roughly the 
  top 18.2% of |gexoflow_z| values. The signals are 
  concentrated near the threshold (87 of 428 signals in the [1.8, 2.0) bucket, 20%).
- **Z-magnitude gradient**: see section 5. The bucket P&L pattern is what it is — 
  read it before drawing conclusions.
- **Volatility overlap**: OMEN-signal bars run at materially higher realized vol 
  than the population median (1.07× higher), but a large share of 
  OMEN signals do NOT fall in the top-5% vol bin. The two selectors agree often 
  but are not identical.

**This descriptive analysis does NOT substitute for the Tier 5.3 permutation test result** (p=0.14, cannot reject the null that GEX features are noise). Tier 5.3 is 
the primary statistical evidence on the predictive-edge question. Q9 only 
characterizes *where* signals fire and whether the location matches the mechanism 
story; not whether the mechanism produces edge.

## 8. Implications for the OMEN-minus-SL forward test

The bucket-extremes spread ($+152/trade) is large relative to the 
typical per-trade P&L scale. The signal-set average is being pushed up by the 
extreme bucket and pulled down by the threshold-clearing bucket.

Two readings, both consistent with the data:
- **Mechanism-carrying reading**: extreme |gex_z| > 3 corresponds to genuine 
  dealer-hedging events; the strategy works because those bars carry directional 
  information. Threshold-clearing bars (1.8-2.0) don't carry the mechanism.
- **Labeling-variable reading**: the strategy works on rare bars that share 
  some property other than the mechanism, and |gex_z| > 3 happens to identify 
  them more reliably than |gex_z| ≈ 1.8.

Either reading leaves the OMEN-minus-SL forward test informative about *trading 
edge*, which is the deployment-relevant quantity. The mechanism interpretation 
affects how confidently the result generalizes to other regimes or market 
conditions, not whether the result is meaningful within this market.

**The pre-registered forward test does not require resolving the mechanism question. It only requires that the OMEN-minus-SL and LS-only patterns reproduce on fresh data.** Q9 doesn't change the pre-reg in any way — it provides background on what 
kind of signal the forward test is exercising.

Either interpretation leaves the forward test result informative about *trading 
edge*, which is the deployment-relevant quantity. The mechanism interpretation 
affects how confidently the result generalizes to other regimes, not whether 
the result is meaningful within this market.

**The pre-registered forward test does not require resolving the mechanism question. It only requires that the OMEN-minus-SL and LS-only patterns reproduce on fresh data.**
