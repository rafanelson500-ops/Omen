# Deflated Sharpe Ratio — Flow Burst locked baseline

## Summary

On 174 trades over 80 sessions (Dec 2025 – Apr 2026), the locked Flow Burst baseline produces a per-trade Sharpe of 0.0479 (annualized 1.0954 at a factor of √(252 × 174/80) = 22.8887). The Probabilistic Sharpe Ratio against a zero benchmark is 72.68%. After deflation for selection bias under N=2 trials and non-normality of returns, the Deflated Sharpe Ratio is 53.33% (verdict: **INCONCLUSIVE**). The N-sensitivity table below shows how the verdict moves as the trial count assumption changes.

## Inputs

- Source: `data/analysis/locked_baseline_trades_blackout_lunch.csv`
- Trades: 158
- Sessions: 76
- Trades/day: 2.0789
- Mean per-trade P&L: $26.2896
- Std per-trade P&L (ddof=1): $549.3104
- Skewness (`scipy.stats.skew`, bias=False): +0.280532
- Excess kurtosis (`scipy.stats.kurtosis(fisher=True, bias=False)`): +0.708276

## Sharpe ratios

- Per-trade SR (used in PSR/DSR): **0.047859**
- Annualization factor √(252 · 2.0789) = **22.888747**
- Annualized SR (headline only): **1.095437**

## PSR vs zero

- PSR(SR* = 0, T = 158) = **72.68%**

## DSR sensitivity to N (independent trials)

| N | SR_0 | DSR | Verdict |
|---:|---:|---:|---|
| 2 | 0.041234 | 53.33% | INCONCLUSIVE |
| 3 | 0.067656 | 40.15% | LIKELY OVERFIT |
| 5 | 0.094613 | 27.78% | LIKELY OVERFIT |
| 10 | 0.124918 | 16.57% | LIKELY OVERFIT |
| 20 | 0.150790 | 9.72% | LIKELY OVERFIT |

## Formulas

Canonical Bailey & Lopez de Prado (2014). All sample stats use `scipy.stats.skew(bias=False)` and `scipy.stats.kurtosis(fisher=True, bias=False)` (excess kurtosis).

**Probabilistic Sharpe Ratio:**  
$$\mathrm{PSR}(SR^\*) = \Phi\!\left[\frac{(\hat{SR} - SR^\*)\sqrt{T-1}}{\sqrt{1 - \hat{\gamma}_3\,\hat{SR} + \frac{\hat{\gamma}_4 + 2}{4}\,\hat{SR}^2}}\right]$$

**Variance of SR estimator:**  
$$\widehat{\mathrm{Var}}(\hat{SR}) = \frac{1 - \hat{\gamma}_3\,\hat{SR} + \frac{\hat{\gamma}_4 + 2}{4}\,\hat{SR}^2}{T - 1}$$

**Expected max SR under N i.i.d. trials (Gumbel approximation):**  
$$SR_0 = \sqrt{\widehat{\mathrm{Var}}(\hat{SR})}\cdot\left[(1-\gamma_{em})\Phi^{-1}\!\left(1-\tfrac{1}{N}\right) + \gamma_{em}\Phi^{-1}\!\left(1-\tfrac{1}{N\,e}\right)\right]$$

**Deflated Sharpe Ratio:** $\mathrm{DSR} = \mathrm{PSR}(SR_0)$.

Note: $\hat{\gamma}_4$ is *excess* kurtosis (Fisher). The canonical B&LdP form is written with Pearson kurtosis γ₄ via `((γ₄ - 1)/4)`; substituting γ₄ = excess + 3 yields `((excess + 2)/4)`. For a normal sample (skew=0, excess=0) this evaluates to 0.5, matching Mertens (2002).

## Verdict bands

- DSR > 95%: REAL EDGE
- 50% ≤ DSR ≤ 95%: INCONCLUSIVE
- DSR < 50%: LIKELY OVERFIT
