# Step 0 — data inventory (vol-regime conditioning)

Branch: `analysis/vol-regime-conditioning-throwaway` (throwaway / archive only; never merges to main).
Generated: 2026-05-14T12:44:50

## Disclosure

```
This analysis is exploratory diagnostic work on a consumed corpus
during an active forward test. It is NOT pre-registered. Results
CANNOT authorize any modification to locked OMEN config or pre-reg.

The OMEN trade outcomes on this 146-session corpus have been examined
many times across TRCB-v1, TRCB-v2 Q1-Q9 post-mortems, microprice
continuation, cell exclusion analysis, churn analysis (Steps 5/7),
and other diagnostics. The corpus is heavily consumed and the
project-wide false discovery rate is high.

Any positive finding here can only be honestly evaluated on a future
pre-registered forward window. This diagnostic adds candidate
filters to the post-verdict pre-reg bookmarks, nothing more.

```

## 1. ES 1s bars (backend/data/market/)

| file | size (MB) | symlink → |
|---|---:|---|
| ES_c_0_ohlcv1s_2025-09-08_2025-12-23.parquet | 0.0 | ES_c_0_ohlcv1s_2025-09-08_2026-04-27.parquet |
| ES_c_0_ohlcv1s_2025-09-08_2026-04-27.parquet | 86.3 | — |
| ES_c_0_ohlcv1s_2025-12-26_2026-04-22.parquet | 47.0 | — |
| ES_c_0_ohlcv1s_2025-12-26_2026-04-24.parquet | 47.0 | — |
| ES_c_0_ohlcv1s_2025-12-30_2026-04-24.parquet | 47.8 | — |
| ES_c_0_ohlcv1s_2026-04-06_2026-04-23.parquet | 7.7 | — |
| ES_c_0_ohlcv1s_2026-04-15_2026-04-24.parquet | 4.0 | — |
| ES_c_0_ohlcv1s_2026-04-16_2026-04-23.parquet | 3.2 | — |
| ES_c_0_ohlcv1s_2026-04-22_2026-04-23.parquet | 1.2 | — |
| ES_c_0_ohlcv1s_2026-04-27_2026-04-27.parquet | 0.4 | — |
| ES_c_0_ohlcv1s_2026-04-28_2026-05-11.parquet | 5.6 | — |
| ES_c_0_ohlcv1s_2026-05-12_2026-05-12.parquet | 0.4 | — |
| ES_c_0_ohlcv1s_2026-05-13_2026-05-13.parquet | 0.3 | — |

Total non-symlink size: **250.9 MB**.

**ATR window** (read from `backend/cheese/features.py`, line containing `rolling(N, min_periods=...)`): **14 bars**. This is the canonical OMEN ATR window we will replicate in Step 1; we will NOT modify `features.py`.

## 2. GEX cache (sanity)

- parquet files: 82
- missing sentinels: 2
- range: 2026-01-13 → 2026-05-13

> ⚠ **Note**: no 2025 GEX parquets present. The Step 1 ATR analysis does not depend on GEX (ATR is derived from ES bars only), so this does not block Step 1. Flagged for your awareness — the OOS window covers 2025-09-08 → 2025-12-23.

## 3. VIX data

| path |
|---|
| /Users/rafanelson/Omen/backend/data/analysis/oos_vix_breakdown.csv |
| /Users/rafanelson/Omen/backend/data/analysis/trades_with_vix.csv |
| /Users/rafanelson/Omen/backend/data/analysis/vix_daily.csv |
| /Users/rafanelson/Omen/backend/data/analysis/vix_stratification_results.csv |

## 4. OPRA / options skew data

| path |
|---|
| /Users/rafanelson/Omen/backend/data/opra_statistics_apr22_23.dbn.zst |

## 5. Target trade log (IS + OOS combined, all-bugfixes)

| half | path | exists | trades | sessions | range |
|---|---|---|---:|---:|---|
| IS  | `/Users/rafanelson/Omen/diagnostics/all-bugfixes-baseline/is_all_bugfixes.csv` | True | 257 | 74 | 2025-12-30 → 2026-04-21 |
| OOS | `/Users/rafanelson/Omen/diagnostics/all-bugfixes-baseline/oos_all_bugfixes.csv` | True | 247 | 72 | 2025-09-08 → 2025-12-23 |

**Combined**: 504 trades / 146 sessions.

## 6. Spec reference vs observed

The prompt cites 371 trades / 146 sessions from OneMinL2 Step 5/7. Observed: **504 trades / 146 sessions** in the all-bugfixes IS+OOS combined log.

If those numbers disagree (e.g. 371 ≠ observed), it likely means OneMinL2 Step 5/7 used a different subset (perhaps post-microprice-filter, or only evaluable trades). Flagging for confirmation before Step 1.

## 7. Stop gate

Per spec, **STOP HERE**. Step 1 (ATR conditioning) runs only after you confirm based on this inventory.

Available without further pulls:
- ✅ Step 1 (ATR conditioning) — ES bars are on disk, ATR computed from them.
- ✅ Step 2 (VIX conditioning) — VIX data found.
- ✅ Step 3 (skew filter) — OPRA data found; will require spec confirmation.

