# Vanna / charm correlation diagnostic — Flow Burst feature discovery

## Summary

On 6,168 5-min bars over the locked window (Dec 2025 – Apr 2026), rolling 60-bar Z-scores of the four GEXbot state columns `zvanna`, `ovanna`, `zcharm`, `ocharm` were correlated with forward log returns at horizons 1/3/5/10/25 bars. The strongest cell across all 40 (feature × horizon × method) combinations is **zcharm @ horizon=25 bars**, Spearman = **-0.0517** (p=8.55e-05, n=5758). For intraday futures signals, |ρ| in the 0.05–0.10 range is typical for a useful predictor; below ~0.02 is indistinguishable from noise.

## Methodology

- Window: 2025-12-26 → 2026-04-22, 5-min bars, RTH only.
- GEX resampled with `cheese.gex.resample(freq='5min')` (state cols → `last()` per bar).
- Z-score: `(x - x.rolling(60, min_periods=20).mean()) / x.rolling(60, min_periods=20).std(ddof=0)` (matches `features.py:79-85`).
- Forward log return: `log(close[t+h] / close[t])`.
- Correlations: `scipy.stats.pearsonr` / `spearmanr`, NaN pairs dropped.
- Conditional effect: when |z| > 2.0, signed mean = `sign(z) · fwd_return`; effect_z = signed_mean / SE.


## Correlation table (Pearson + Spearman)

| feature | horizon_bars | n | pearson_r | pearson_p | spearman_r | spearman_p |
|---|---:|---:|---:|---:|---:|---:|
| zvanna | 1 | 5782 | +0.0175 | 1.83e-01 | +0.0155 | 2.40e-01 |
| zvanna | 3 | 5780 | -0.0002 | 9.87e-01 | +0.0093 | 4.78e-01 |
| zvanna | 5 | 5778 | -0.0089 | 5.01e-01 | +0.0040 | 7.61e-01 |
| zvanna | 10 | 5773 | -0.0020 | 8.79e-01 | +0.0108 | 4.12e-01 |
| zvanna | 25 | 5758 | +0.0064 | 6.26e-01 | +0.0079 | 5.49e-01 |
| ovanna | 1 | 5782 | -0.0065 | 6.20e-01 | +0.0015 | 9.08e-01 |
| ovanna | 3 | 5780 | -0.0112 | 3.95e-01 | +0.0035 | 7.91e-01 |
| ovanna | 5 | 5778 | -0.0087 | 5.10e-01 | -0.0051 | 6.97e-01 |
| ovanna | 10 | 5773 | -0.0224 | 8.94e-02 | -0.0174 | 1.87e-01 |
| ovanna | 25 | 5758 | -0.0168 | 2.02e-01 | +0.0034 | 7.96e-01 |
| zcharm | 1 | 5782 | -0.0360 | 6.19e-03 | +0.0027 | 8.35e-01 |
| zcharm | 3 | 5780 | -0.0750 | 1.15e-08 | -0.0146 | 2.66e-01 |
| zcharm | 5 | 5778 | -0.0837 | 1.83e-10 | -0.0199 | 1.31e-01 |
| zcharm | 10 | 5773 | -0.0854 | 8.28e-11 | -0.0396 | 2.59e-03 |
| zcharm | 25 | 5758 | -0.0416 | 1.60e-03 | -0.0517 | 8.55e-05 |
| ocharm | 1 | 5782 | -0.0110 | 4.02e-01 | -0.0006 | 9.62e-01 |
| ocharm | 3 | 5780 | -0.0190 | 1.49e-01 | -0.0003 | 9.79e-01 |
| ocharm | 5 | 5778 | -0.0184 | 1.61e-01 | -0.0095 | 4.72e-01 |
| ocharm | 10 | 5773 | -0.0336 | 1.08e-02 | -0.0228 | 8.30e-02 |
| ocharm | 25 | 5758 | -0.0203 | 1.23e-01 | +0.0039 | 7.66e-01 |

## Conditional return effect (|z| > 2.0)

| feature | horizon_bars | n_cond | uncond_mean_ret | cond_signed_mean_ret | effect_z |
|---|---:|---:|---:|---:|---:|
| zvanna | 1 | 665 | +0.000004 | +0.000051 | +1.161 |
| zvanna | 3 | 665 | +0.000012 | -0.000063 | -0.755 |
| zvanna | 5 | 665 | +0.000021 | -0.000202 | -1.926 |
| zvanna | 10 | 665 | +0.000050 | -0.000165 | -1.120 |
| zvanna | 25 | 654 | +0.000106 | +0.000429 | +2.053 |
| ovanna | 1 | 886 | +0.000004 | -0.000023 | -0.483 |
| ovanna | 3 | 886 | +0.000012 | -0.000024 | -0.300 |
| ovanna | 5 | 886 | +0.000021 | -0.000045 | -0.449 |
| ovanna | 10 | 884 | +0.000050 | -0.000155 | -1.193 |
| ovanna | 25 | 882 | +0.000106 | -0.000020 | -0.125 |
| zcharm | 1 | 917 | +0.000004 | -0.000033 | -0.522 |
| zcharm | 3 | 915 | +0.000012 | -0.000173 | -1.557 |
| zcharm | 5 | 913 | +0.000021 | -0.000309 | -2.261 |
| zcharm | 10 | 910 | +0.000050 | -0.000398 | -2.132 |
| zcharm | 25 | 901 | +0.000106 | -0.000072 | -0.287 |
| ocharm | 1 | 927 | +0.000004 | -0.000017 | -0.380 |
| ocharm | 3 | 927 | +0.000012 | -0.000018 | -0.235 |
| ocharm | 5 | 927 | +0.000021 | -0.000041 | -0.407 |
| ocharm | 10 | 925 | +0.000050 | -0.000127 | -0.985 |
| ocharm | 25 | 923 | +0.000106 | +0.000028 | +0.169 |

## Interaction with `gexoflow_z > 2.0`

| feature_z | horizon_bars | n_gex_alone | mean_ret_gex_alone | n_both_gates | mean_ret_both_gates | n_total_gex_gate | mean_ret_full_gex_gate | delta_mean_ret | welch_t |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| zvanna_z | 1 | 171 | +0.000191 | 13 | +0.000694 | 184 | +0.000226 | +0.000504 | +1.034 |
| zvanna_z | 3 | 171 | +0.000331 | 13 | +0.001310 | 184 | +0.000400 | +0.000979 | +1.348 |
| zvanna_z | 5 | 171 | +0.000453 | 13 | +0.001394 | 184 | +0.000520 | +0.000940 | +1.208 |
| zvanna_z | 10 | 170 | +0.000486 | 13 | +0.001554 | 183 | +0.000561 | +0.001068 | +1.101 |
| zvanna_z | 25 | 168 | +0.000477 | 13 | -0.000253 | 181 | +0.000425 | -0.000730 | -0.416 |
| zcharm_z | 1 | 122 | +0.000299 | 62 | +0.000084 | 184 | +0.000226 | -0.000215 | -0.515 |
| zcharm_z | 3 | 122 | +0.000529 | 62 | +0.000146 | 184 | +0.000400 | -0.000383 | -0.582 |
| zcharm_z | 5 | 122 | +0.000701 | 62 | +0.000162 | 184 | +0.000520 | -0.000539 | -0.738 |
| zcharm_z | 10 | 121 | +0.000789 | 62 | +0.000118 | 183 | +0.000561 | -0.000671 | -0.739 |
| zcharm_z | 25 | 119 | +0.000477 | 62 | +0.000324 | 181 | +0.000425 | -0.000153 | -0.132 |

## Per-feature verdicts

Thresholds: SIGNAL = |Spearman| > 0.05 with p < 0.01 at any horizon; WEAK = |Spearman| > 0.02 but not clearing SIGNAL; otherwise NOISE.

| feature | verdict | best cell |
|---|---|---|
| zvanna | **NOISE** | max |Spearman| at horizon=1 = +0.0155 (p=2.40e-01) |
| ovanna | **NOISE** | max |Spearman| at horizon=10 = -0.0174 (p=1.87e-01) |
| zcharm | **SIGNAL** | horizon=25  Spearman=-0.0517 (p=8.55e-05, n=5758) |
| ocharm | **WEAK** | horizon=10  Spearman=-0.0228 (p=8.30e-02, n=5773) |

## Caveats

- Vanna/charm are aggregated by `gex.resample()` as **state** columns (last value per bar) rather than as flows. The Z-score is therefore taken over a bar-end snapshot, not over a per-bar integrated quantity. A flow-style aggregation (1s deltas summed within a bar) would require a separate resample path and is out of scope here.
- Intraday correlations of 0.05–0.10 are typical magnitudes for useful predictors; below 0.02 is noise. Treat the verdict thresholds accordingly.
- 80-day window. Findings are exploratory; a multi-quarter sample would be needed before any production use.
- Descriptive analysis only. No filter recommendations.
