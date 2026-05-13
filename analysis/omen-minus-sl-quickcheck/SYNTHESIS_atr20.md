# OMEN-minus-SL — ATR=20 SENSITIVITY VARIANT (THROWAWAY)

Branch: `analysis/omen-minus-sl-quickcheck-throwaway` (throwaway / archive only; never merges to main).
Generated: 2026-05-12T21:02:51

## 1. Disclosure

This is a SENSITIVITY VARIANT of the original OMEN-minus-SL quick-check 
(see `SYNTHESIS.md` in the same directory). It runs the identical pipeline 
on the identical fresh-session window, with ONE change: the ATR rolling 
window for stop/target sizing is switched from **14 → 20**.

Motivation: `Current_State_of_OMEN.txt` documented `atr_window_bars=20` 
but the actual locked code (`backend/cheese/features.py:54`) hardcodes 
a 14-bar SMA. This run quantifies whether the documentation/code mismatch 
changes the fresh-18 read in a directionally meaningful way.

**The same caveats from the original quick-check apply:** sample size 
(18 trades, 8 sessions) is far below what's required for any verdict. 
This sensitivity check does NOT validate or invalidate OMEN-minus-SL.

**The ATR=20 fresh result is NOT directly comparable to the IS-174 / 
OOS-158 baselines** (those ran on ATR=14). The valid comparison here 
is fresh-18 ATR=14 vs fresh-18 ATR=20.

## 2. Implementation

- Same fresh-session window: 8 sessions, 2026-04-30 → 2026-05-11.
- Same locked params: flow_burst z=1.8, blackout_lunch=True, stop=2.0×ATR, target=4.5×ATR, time_stop=25min, bar_freq=5min.
- ATR override: after `features.build_features` returns, the `atr` and 
  `atr_pts` columns are recomputed as `tr.rolling(20, min_periods=5).mean()`. 
  Same True Range formula as `features.py:54`, only the window changes.
- No locked files modified.
- Warmup start shifted back 1 week (2026-04-08) to give ATR(20) more bars to stabilize.

## 3. Side-by-side comparison

| metric | ATR=14 (original) | ATR=20 (this run) |
|---|---:|---:|
| N total trades | 18 | 18 |
| Cell counts (LL/LS/SL/SS) | 2/6/1/9 | 2/6/1/9 |
| Full OMEN win rate | 61.1% | 61.1% |
| Full OMEN mean $ | $+4.72 | $+34.58 |
| Full OMEN sum $ | $+85 | $+622 |
| Full OMEN Sharpe | +0.30 | +2.27 |
| Full OMEN max DD | $-1251 | $-1026 |
| OMEN-minus-SL N | 17 | 17 |
| OMEN-minus-SL win rate | 64.7% | 64.7% |
| OMEN-minus-SL mean $ | $+29.93 | $+62.28 |
| OMEN-minus-SL sum $ | $+509 | $+1059 |
| OMEN-minus-SL Sharpe | +1.84 | +4.07 |

## 4. Per-cell breakdown — ATR=20

| cell | N | mean $ | sum $ |
|---|---:|---:|---:|
| LONG_long | 2 | $+438.75 | $+878 |
| LONG_short | 6 | $+87.71 | $+526 |
| SHORT_long | 1 | $-436.25 | $-436 |
| SHORT_short | 9 | $-38.33 | $-345 |

## 5. Per-trade overlay (matched on entry_time + side + gamma_regime)

FlowBurst entries depend only on `gexoflow_z` / `dexoflow_z`, which are 
ATR-independent. So all 18 ATR=14 entry points are expected to match all 
18 ATR=20 entry points. Differences are confined to:
- `atr_at_entry` (driven by the ATR window)
- `stop_px` / `target_px` (sized as ATR multiples)
- `exit_reason`, `bars_held`, `exit_px`, `net_dollars` (downstream of the above)

- Matched trades: **18 / 18**
- Trades with same `exit_reason`: 16 / 18
- Δ net_dollars (ATR=20 − ATR=14): mean = **$+29.86**, sum = **$+538**, range = [$-37.50, $+337.50]

## 6. Honest comparison

**Did the trade count change?** 
No. Both runs produced **18** trades. This is expected: 
FlowBurst entry conditions depend only on gexoflow_z / dexoflow_z, which 
are computed from GEX flow features and have no dependence on ATR. The 
ATR change only affects stop/target sizing on the same set of entries.

**Did the cell composition change?**
 No. Cell counts are identical across the two runs.

**Did the directional verdict change?**
 ATR=14: minus-SL Sharpe +1.84 vs full Sharpe +0.30 → directionally CONSISTENT.
 ATR=20: minus-SL Sharpe +4.07 vs full Sharpe +2.27 → directionally CONSISTENT.
 **Same directional verdict on both ATR windows.**

**Is the result still driven by removing a single SHORT_long trade?**
 ATR=14 SHORT_long: n=1, sum=$-424.
 ATR=20 SHORT_long: n=1, sum=$-436. 
 Yes — both runs have a single SHORT_long trade. The minus-SL 
 Sharpe lift in BOTH cases is driven by removing that one trade. 
 Same fragility caveat from the original quick-check applies.

## 7. Interpretation

### Direction unchanged, magnitude shifted substantially

- **Trade count and cell composition: identical** (18 trades, LL/LS/SL/SS = 2/6/1/9 in both runs). 
  Expected: FlowBurst entries depend only on `gexoflow_z`/`dexoflow_z`, both 
  ATR-independent.

- **Directional verdict (minus-SL > full): unchanged**. Both ATR windows 
  produce DIRECTIONALLY CONSISTENT.

- **Sharpe magnitudes shift substantially**: full Sharpe goes +0.30 → +2.27 (Δ = +1.97); minus-SL Sharpe goes +1.84 → +4.07 (Δ = +2.22). The directional label is preserved but the 
  underlying performance is **noticeably better at ATR=20** on this sample.

- **PnL shift on matched trades**: Δ net_dollars (ATR=20 − ATR=14) sums to **$+538** across 18 trades (mean **$+29.86/trade**). 
  Most of the lift comes from the **SHORT_short** cell 
(n=9, sum=$-908 at ATR=14 
vs $-345 at ATR=20 — a swing of $+562).

### What this means

- **Trade selection is ATR-invariant in this strategy.** Entries don't care.

- **Exit outcomes are ATR-sensitive**, especially in the SHORT_short cell. 
  ATR=20 produces slightly wider stops (median ATR 5.96 vs 5.79), which 
  reduces stop-outs and lets trades reach time-stop / target.

- **For the OMEN-minus-SL hypothesis specifically**: both ATR windows give 
  the same directional read (minus-SL > full) and both still rest on the 
  same n=1 SHORT_long trade. The hypothesis-level conclusion is unchanged.

- **The documentation/code mismatch is NOT cosmetic.** ATR=20 would produce 
  meaningfully different Sharpe numbers on the IS-174 / OOS-158 baselines 
  if those were re-run with this ATR window. Those Sharpes ARE NOT REPRODUCIBLE 
  under ATR=20 without re-running the full backtest. If `Current_State_of_OMEN.txt` 
  is the source of truth for what's deployed, either the doc is wrong or the 
  code is wrong; pick one and reconcile before deployment.

### Limits on this read

- 18 trades is far too small to claim ATR=20 is 'better' than ATR=14 for 
  OMEN's edge. The Sharpe lift could be coincidence on this window.
- The ATR=20 fresh result is NOT comparable to IS-174 / OOS-158 — those used 
  ATR=14. To make a clean ATR=14 vs ATR=20 statement at scale, both ATR windows 
  would need to be re-run on the full 160-session corpus. That's a separate 
  exercise and consumed-data caveats apply.

## 8. Caveats (mandatory)

- **18 trades is too small for any verdict.** This holds regardless of ATR window.
- **ATR=20 fresh result is NOT directly comparable to IS-174 or OOS-158** 
  (those were generated with ATR=14). The valid comparison is fresh-18 
  ATR=14 vs fresh-18 ATR=20, both shown above.
- **This sensitivity test does NOT validate or invalidate OMEN-minus-SL.** 
  It only quantifies the ATR-window-dependence of the fresh-18 read.
- **Forward-test pre-registration on 30+ accumulated sessions remains 
  required.** That is the only path to a verdict, regardless of which ATR 
  window OMEN ultimately uses.
- **The original quick-check's fragility note also applies here**: the 
  minus-SL Sharpe lift in both ATR variants rests on removing a single 
  SHORT_long trade. SHORT_short (n=9) is doing more total $ damage than 
  SHORT_long (n=1) in both runs.
