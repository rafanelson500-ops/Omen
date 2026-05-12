# TRCB-v1 Post-Mortem Q2 — Window length sensitivity

**Re-stream of MBP-10 with 4 window lengths.** Locked parameters identical to TRCB-v1 except window length; 25-min forward return horizon held fixed.

**Data:** `analysis/trcb-postmortem/per_bar_volumes_multiwindow.parquet` (12,480 bars × 160 sessions)

**60s sanity check** against Phase 2 `per_bar_volumes.parquet`: buy_vol diffs = 0, sell_vol diffs = 0 on 12,480 merged rows.

## Comparison table

| window | n_long | n_short | n_trig | trig_rate | mean_fwd_25min (signed) | t vs 0 | sep vs uncond | % > 0 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 30s | 38 | 33 | 71 | 0.5922% | +1.5775 | +2.3151 | +1.5257 | 63.4% |
| 60s | 15 | 12 | 27 | 0.2252% | -0.9630 | -0.4150 | -1.0126 | 55.6% |
| 120s | 6 | 1 | 7 | 0.0584% | +0.1786 | +0.0643 | +0.1264 | 57.1% |
| 300s | 1 | 0 | 1 | 0.0083% | — | — | — | 100.0% |

## Reading

- Best window by separation-vs-unconditional: **30s** (sep = +1.5257, n_trig = 71, t = +2.3151)
- Worst window by separation-vs-unconditional: **60s** (sep = -1.0126, n_trig = 27)
- 60s (locked TRCB-v1): sep = -1.0126, n_trig = 27

## Caveats

- Sample sizes (n_trig) per window are small (single-digit to mid-double-digit). t-stats with these n values are noisy and should not be treated as evidence of mechanism existence at a particular window.
- This is a 4-point sweep, not a continuous sensitivity curve.
- 25-min forward return horizon is fixed for cross-window comparability. Q3 varies the horizon separately on the locked-60s triggered bars.

## Disclaimer

Diagnostic only. TRCB-v1 FAIL verdict unaffected. No new filter authorized.
