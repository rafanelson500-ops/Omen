# Tier 5.3 GEX permutation test — bugfixed re-run (THROWAWAY)

Branch: `analysis/gex-permutation-bugfixed-throwaway` (throwaway / archive only; never merges to main).
Generated: 2026-05-13T01:35:40

## 1. Disclosure

## DISCLOSURE — methodology re-run on consumed corpus

This re-runs the existing Tier 5.3 GEX permutation test on the 160-session
corpus using the bugfixed features.py and backtest.py (session-boundary
fix, time-stop off-by-one fix, trade overlap fix). The original Tier 5.3
result was p=0.14 on buggy code.

This is a methodology correction, not a new hypothesis. The corpus has
been used for multiple prior analyses. A p-value below 0.05 here would
indicate the GEX mechanism question becomes more answerable under correct
math, but cannot serve as standalone validation given the consumed-data
status.


## 2. Original Tier 5.3 result (reference)

- Methodology: within-session row shuffle of GEX raw data, 200 permutations, locked-baseline OMEN on Sep 8 → Dec 23 2025 OOS window.
- Original p-value (Sharpe): **p = 0.14** (cannot reject null at α=0.05).
- Code at the time contained the session-boundary bug, time-stop off-by-one, and exit/entry overlap bug. All three are now fixed on main.

## 3. Real bugfixed baseline (target)

- Window: 2025-09-08 → 2025-12-23 (same OOS window as the original test).
- Real trade count: **247** (bugfixed; previously 158).
- Real Sharpe (`sharpe_daily` from metrics.summarize): **+0.3082**
- Real profit factor: **+1.0503**
- Real total PnL: **$+2,046.25**

Note: `sharpe_daily` is the daily-scale Sharpe produced by 
`metrics.summarize` (the same metric the original test used). It is 
NOT the same number as the annualized Sharpe (+0.51) cited elsewhere for the 
same OOS window. The annualized scaling differs; the p-value computation is 
valid because real and permuted distributions both use the same scale.

## 4. Bugfixed simple-shuffle result

Methodology: shuffle GEX row order WITHIN each trading session (preserves daily totals, destroys within-session temporal structure). 
Same as the original Tier 5.3 method; only the underlying features.py + 
backtest.py code is now bugfixed.

- N permutations: **500**, seed = 42
- Permuted Sharpe distribution:
  - mean: -0.3981
  - median: -0.3730
  - std: +1.0577
  - quantiles: q05=-2.1663  q25=-1.1245  q75=+0.3560  q95=+1.3504
  - range: [-3.7628, +2.3188]
- **Real Sharpe** (+0.3082) was beaten by **133 / 500** permuted Sharpes.
- **p-value (Sharpe): 0.2660**
- p-value (profit factor): 0.3100
- p-value (total PnL): 0.2000

## 5. Bugfixed block-permutation result

Methodology: divide the 76 trading sessions into non-overlapping blocks of 5 
sessions; permute the block order; concatenate. Preserves within-session 
temporal order AND short-range (5-session) autocorrelation. More rigorous for 
financial time series.

- N permutations: **500**, block size = 5 sessions, seed = 42
- Permuted Sharpe distribution:
  - mean: -0.4070
  - median: -0.4136
  - std: +1.0967
  - quantiles: q05=-2.1356  q25=-1.2332  q75=+0.3504  q95=+1.3955
  - range: [-3.5511, +2.6886]
- **Real Sharpe** (+0.3082) was beaten by **131 / 500** permuted Sharpes.
- **p-value (Sharpe): 0.2620**
- p-value (profit factor): 0.2680
- p-value (total PnL): 0.2100

## 6. Comparison table

| methodology | N perms | p (Sharpe) | p (PF) | p (PnL) | reading |
|---|---:|---:|---:|---:|---|
| Original Tier 5.3 (buggy code) | 200 | 0.14 | — | — | cannot reject null |
| Bugfixed simple shuffle | 500 | **0.2660** | 0.3100 | 0.2000 | no evidence against null |
| Bugfixed block permutation (5-session) | 500 | **0.2620** | 0.2680 | 0.2100 | no evidence against null |

## 7. Honest interpretation

- **Simple-shuffle p-value moved from 0.14 (buggy) to 0.2660 (bugfixed)** — change of +0.1260.
- **Block-permutation p-value: 0.2620** (no prior comparison; this methodology not run on buggy code).

Under the bugfixed simple-shuffle methodology, the test shows **even less 
evidence against the null** than the buggy version. The original p=0.14 was 
if anything understating the difficulty of detecting GEX signal.

Simple-shuffle and block-permutation p-values are close (Δ = 0.004). Time-series autocorrelation is not 
doing meaningful work in the test on this data. Both methodologies tell the 
same story.

## 8. Implications for the OMEN-minus-SL forward test (pre-reg `9c1c22f`)

**Pre-reg is unchanged regardless of this result.** The pre-registered forward 
test is about trading edge, not mechanism interpretation. Both arms remain locked:

- Hypothesis 1 (OMEN-minus-SL): PASS gate Sharpe ≥ 1.20 + minus-SL ≥ full + 0.50
- Hypothesis 2 (LS-only): PASS gate Sharpe ≥ 1.00 on minimum 30 LS trades

This Q-suffix diagnostic affects only the interpretive frame around the forward 
test:
- The mechanism question remains uncertain even under bugfixed math. 
  Forward test still informs trading edge regardless — the deployment-
  relevant quantity does not require the mechanism question to be resolved.

## 9. Caveats

- Consumed-corpus analysis. The 76-session OOS window has been used for many 
  prior analyses.
- p-values from a single permutation test can vary modestly with the random 
  seed (small Monte Carlo error). N=500 keeps the standard error on p around 
  ±0.022.
- This does not constitute new validation; only a methodological correction of 
  an existing test.
- Block size = 5 sessions is the default per the prompt. A different block size 
  could give a different p-value; this is not a knob to be tuned post-hoc.
- The bugfixed real Sharpe is computed on the same 247-trade bugfixed OOS log 
  used as the locked baseline elsewhere. Permuted runs use the same Sharpe 
  metric (`sharpe_daily`), so the p-value comparison is internally consistent.
