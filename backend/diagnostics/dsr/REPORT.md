# Deflated Sharpe Ratio — Flow Burst locked baseline

## Summary

On 174 trades over 80 sessions (Dec 2025 – Apr 2026), the locked Flow Burst baseline produces a per-trade Sharpe of 0.2193 (annualized 5.1347 at a factor of √(252 × 174/80) = 23.4115). The Probabilistic Sharpe Ratio against a zero benchmark is 99.90%. After deflation for selection bias under N=20 trials and non-normality of returns, the Deflated Sharpe Ratio is 88.36% (verdict: **INCONCLUSIVE**). The N-sensitivity table below shows how the verdict moves as the trial count assumption changes.

## Inputs

- Source: `data/analysis/locked_baseline_trades_blackout_lunch.csv`
- Trades: 174
- Sessions: 80
- Trades/day: 2.1750
- Mean per-trade P&L: $141.6595
- Std per-trade P&L (ddof=1): $645.8906
- Skewness (`scipy.stats.skew`, bias=False): +0.741876
- Excess kurtosis (`scipy.stats.kurtosis(fisher=True, bias=False)`): +0.678966

## Sharpe ratios

- Per-trade SR (used in PSR/DSR): **0.219324**
- Annualization factor √(252 · 2.1750) = **23.411536**
- Annualized SR (headline only): **5.134718**

## PSR vs zero

- PSR(SR* = 0, T = 174) = **99.90%**

## DSR sensitivity to N (independent trials)

| N | SR_0 | DSR | Verdict |
|---:|---:|---:|---|
| 10 | 0.111630 | 93.56% | INCONCLUSIVE |
| 15 | 0.125532 | 90.71% | INCONCLUSIVE |
| 20 | 0.134750 | 88.36% | INCONCLUSIVE |
| 30 | 0.146992 | 84.62% | INCONCLUSIVE |
| 50 | 0.161378 | 79.31% | INCONCLUSIVE |

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
