# TRCB-v1 Post-Mortem Q3 — Forward-return horizon sensitivity

**Source:** locked-60s triggered set from Phase 2 (n=27: 15 long + 12 short)

**Horizons evaluated:** [1, 5, 15, 25, 60] minutes

**Unconditional baseline:** raw (no direction) forward return on 11,992 evaluable bars at each horizon.

## Combined triggered set (both directions, signed)

| horizon (min) | n | mean signed | t vs 0 | % > 0 | uncond mean | sep vs uncond |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 27 | +2.7778 | +9.4785 | 100.0% | -0.0177 | +2.7954 |
| 5 | 27 | +1.6019 | +1.5418 | 59.3% | +0.0005 | +1.6013 |
| 15 | 27 | -0.8704 | -0.4560 | 33.3% | +0.0305 | -0.9009 |
| 25 | 27 | -0.9630 | -0.4150 | 55.6% | +0.0488 | -1.0117 |
| 60 | 27 | -3.6204 | -0.8116 | 48.1% | +0.1393 | -3.7597 |

## Per-direction breakdown

| horizon (min) | long_n | long_mean | long_%pos | short_n | short_mean | short_%pos |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 15 | +2.6500 | 100.0% | 12 | +2.9375 | 100.0% |
| 5 | 15 | +0.6500 | 46.7% | 12 | +2.7917 | 75.0% |
| 15 | 15 | -0.5333 | 26.7% | 12 | -1.2917 | 41.7% |
| 25 | 15 | +1.5333 | 66.7% | 12 | -4.0833 | 41.7% |
| 60 | 15 | -6.8333 | 46.7% | 12 | +0.3958 | 50.0% |

## Reading

- Best horizon by signed mean: **1 min** (mean = +2.7778, n = 27)
- Best horizon by t-statistic: **1 min** (t = +9.4785, mean = +2.7778)
- 25-min horizon (Phase 2 default): mean = -0.9630, t = -0.4150

## Caveats

- n=27 is small. t-statistics with this sample size are noisy. **Do not overclaim**: even an apparently significant t at any horizon is consistent with random variation given the multiple-horizon look.
- Short-side n=12 and long-side n=15 are even smaller subsets — per-direction means are highly volatile.
- Forward return at 60min frequently rolls outside RTH; same-session check drops bars whose horizon would land past 16:00 ET.

## Disclaimer

Diagnostic only. TRCB-v1 FAIL verdict unaffected. No new filter authorized.
