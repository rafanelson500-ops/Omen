# TRCB-v1 Post-Mortem Q1 — Delta ratio distribution

**Source:** `diagnostics/mbp10-trcb-v1/per_bar_volumes.parquet` (12,480 bars, 12,254 with ≥1 trade in 60s window)

**Locked TRCB-v1 P3 threshold:** ratio ≥ 2.0

## Distribution stats

- Mean `ratio_dominant`: **1.1949**
- Median `ratio_dominant`: **1.1478**

### Percentiles

| percentile | ratio_dominant |
|---:|---:|
| 50.0th | 1.1478 |
| 60.0th | 1.1885 |
| 70.0th | 1.2396 |
| 75.0th | 1.2702 |
| 80.0th | 1.3089 |
| 85.0th | 1.3577 |
| 90.0th | 1.4248 |
| 92.5th | 1.4700 |
| 95.0th | 1.5352 |
| 97.5th | 1.6477 |
| 99.0th | 1.8190 |
| 99.5th | 1.9927 |

### Where does the locked 2.0 threshold sit?

- **99.52th percentile** of dominant-side ratio (i.e. 0.48% of evaluable bars clear it).
- This is the **per-bar dominant-side** rate. Long-only and short-only
  rates are roughly half of this (≈0.27% each in Phase 2 results).

### Top-tail thresholds (what ratio would isolate each tail)

| tail | ratio_dominant threshold |
|---|---:|
| top 10% | ≥ 1.4248 |
| top  5% | ≥ 1.5352 |
| top  1% | ≥ 1.8190 |

## Histogram (1.0 → 5.0+, 20 bins)

| bin | n | % |
|---|---:|---:|
| [1.00, 1.21) | 7,897 | 64.44% |
| [1.21, 1.42) | 3,100 | 25.30% |
| [1.42, 1.63) | 918 | 7.49% |
| [1.63, 1.84) | 223 | 1.82% |
| [1.84, 2.05) | 74 | 0.60% |
| [2.05, 2.26) | 27 | 0.22% |
| [2.26, 2.47) | 10 | 0.08% |
| [2.47, 2.68) | 2 | 0.02% |
| [2.68, 2.89) | 2 | 0.02% |
| [2.89, 3.11) | 1 | 0.01% |
| [3.11, 3.32) | 0 | 0.00% |
| [3.32, 3.53) | 0 | 0.00% |
| [3.53, 3.74) | 0 | 0.00% |
| [3.74, 3.95) | 0 | 0.00% |
| [3.95, 4.16) | 0 | 0.00% |
| [4.16, 4.37) | 0 | 0.00% |
| [4.37, 4.58) | 0 | 0.00% |
| [4.58, 4.79) | 0 | 0.00% |
| [4.79, 5.00) | 0 | 0.00% |
| ≥5.00 | 0 | 0.00% |

## Segmented percentiles

### By hour of day (ET)

| hour | n | p50 | p75 | p90 | p95 | p99 | % < 2.0 |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 09 | 800 | 1.1045 | 1.2010 | 1.3137 | 1.3664 | 1.4702 | 100.00% |
| 10 | 1,920 | 1.1233 | 1.2296 | 1.3544 | 1.4519 | 1.7424 | 99.58% |
| 11 | 1,920 | 1.1350 | 1.2558 | 1.3968 | 1.4956 | 1.7540 | 99.79% |
| 12 | 1,920 | 1.1582 | 1.2852 | 1.4635 | 1.5894 | 1.9300 | 99.11% |
| 13 | 1,902 | 1.1693 | 1.2969 | 1.4674 | 1.5869 | 1.9280 | 99.32% |
| 14 | 1,896 | 1.1644 | 1.3031 | 1.4575 | 1.5456 | 1.8509 | 99.47% |
| 15 | 1,896 | 1.1669 | 1.2817 | 1.4466 | 1.5612 | 1.8379 | 99.63% |

### By day of week

| dow | n | p50 | p75 | p90 | p95 | p99 | % < 2.0 |
|---|---:|---:|---:|---:|---:|---:|---:|
| Monday | 2,387 | 1.1561 | 1.2911 | 1.4373 | 1.5598 | 1.8553 | 99.33% |
| Tuesday | 2,618 | 1.1506 | 1.2868 | 1.4448 | 1.5552 | 1.8573 | 99.54% |
| Wednesday | 2,508 | 1.1497 | 1.2741 | 1.4225 | 1.5328 | 1.8447 | 99.48% |
| Thursday | 2,310 | 1.1405 | 1.2522 | 1.3995 | 1.4989 | 1.7703 | 99.61% |
| Friday | 2,431 | 1.1395 | 1.2521 | 1.4071 | 1.5148 | 1.7297 | 99.63% |

### VIX regime — SKIPPED per task instructions

## Reading

- 2.0 sits at the 99.52th percentile of `ratio_dominant`. The threshold was effectively asking for a top-tail event by construction. **Structurally rare** — the rarity is in P3 alone, not in P3 ∩ P2 ∩ P4.

## Disclaimer

This is descriptive analysis on already-locked data. The TRCB-v1 FAIL verdict is unaffected. No new filter run is authorized.
