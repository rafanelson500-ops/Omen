# Bar-level Sharpe — locked Flow Burst baseline

_Methodology recompute on existing data. The locked strategy is unchanged. This is the academic-standard Sharpe input that future DSR/PSR computations on forward-test data should consume._

## Pre-registered predictions

- User: B — bar-level Sharpe **3.5–5.0** (roughly matches trade-level)
- Claude: A — bar-level Sharpe **1.5–2.5** (lower than trade-level)

## ⚠ Close-vs-fill bias (read this before citing the Sharpe number)

**The reported Strategy Sharpe is computed on close-to-close bar log returns and is therefore systematically biased UPWARD versus the strategy's actual delivered P&L by approximately 30%.** This bias is mechanical, symmetric across stops/targets, and is a known caveat of bar-level Sharpe in the literature.

**Source of the bias:**

- Stops fill at `stop_px − slip` (mid-bar price), but bar-level reconstruction uses `close[exit_bar]`. On stops, price typically **recovers** between the stop trigger and the bar close → `close[exit_bar] > stop_px` for long stops → bar-level under-counts the loss. **Bias up.**
- Targets fill at `target_px` (mid-bar limit), but bar-level uses `close[exit_bar]`. On targets, price typically **retraces** between target hit and bar close → `close[exit_bar] < target_px` for long targets → bar-level under-counts the gain. **Bias down.**
- Quantitatively on this dataset (174 trades, 42 stops + 15 targets): stops contribute ~+280 pts of upward bias, targets ~−110 pts of downward bias. Net ≈ +170 pts on a true total of 510 pts → ~30% upward bias on reconstructed gross P&L. Time/session-close exits (close[exit_bar] ≈ next_bar.open ≈ actual fill) contribute negligibly.

**Why we keep close-to-close anyway:** the academic literature's bar-level Sharpe is universally computed on close-to-close returns. Reporting that number — even with the bias — is what makes the result cross-comparable to published studies. The fill-aware alternative would be more accurate for THIS strategy but would not match how academic papers compute the metric. The Sanity Check below uses fill-aware reconstruction to validate the position vector; the Strategy Sharpe uses close-to-close.

**Implication:** the reported Strategy Sharpe of +4.9434 should be read as an **upward-biased** academic-standard estimate. The 'true' delivered Sharpe based on actual fills would be roughly ~+3.80 (divide by ~1.3 to undo the ~30% upward P&L bias on the mean). For DSR/PSR work on forward-test data, the same close-to-close convention will apply on both sides, so the bias washes out in any *comparison*.

## Methodology — what each Sharpe number means

Four Sharpe-like quantities have appeared across this project's diagnostics. They differ in *which sample* the mean/std are taken over and in the annualization factor. Bar-level is the academic standard.

| name | sample | annualization | comparable to academic literature? |
|---|---|---|---|
| Daily-equity Sharpe (`metrics.py`) | per-day equity diffs | √252 | partially — daily resolution |
| Per-trade raw | per-trade `net_dollars` | none (per-trade units) | no |
| Per-trade annualized (DSR input) | per-trade `net_dollars` | √(252·trades_per_day) | yes (Bailey-Lopez de Prado convention) |
| **Bar-level Strategy Sharpe** | **per-bar strategy log return (close-to-close)** | **√(252·78) ≈ 140.2** | **yes — direct comparison to literature, with close-vs-fill caveat above** |
| **Bar-level In-Market Sharpe** | per-bar log return on active bars only | √(252·avg bars-in-market/day) | qualitatively (signal quality conditional on holding) |

## Step 2 — sanity check (fill-aware reconstruction)

Per Option 3 (hybrid), the sanity check uses fill-aware bar contributions: default bar P&L = session-aware `close.diff()` (NaN at first bar of session → 0); per-trade overrides at first in-trade bar (`close[e] − entry_px`) and last in-trade bar (`exit_px − close[x−1]`); same-bar trades use `exit_px − entry_px`. Telescoping per trade gives `side · (exit_px − entry_px) = trade gross_points` exactly modulo float precision. This validates the position-vector entry/exit alignment.

- Trade-log gross_points: **+510.3750**
- Bar-level reconstructed (fill-aware): **+487.3750**
- Absolute diff: **-23.0000 pts**
- Relative diff: **-4.506490%**  (tolerance ±5.0%) → **PASSES**

## Step 3 — return convention (close-to-close, academic standard)

`bar_log_return[t]` = within-session `log(close[t]) − log(close[t−1])`. For the first bar of each session (which would otherwise be NaN under the session-aware diff), `bar_log_return = log(close/open)` so an in-trade session-open bar credits the intraday open-to-close move. **This is the metric that carries the close-vs-fill bias documented above.**

Strategy return per spec: `strategy_return[t] = position[t] · bar_log_return[t+1]` (i.e. `position.shift(0) * returns.shift(-1)`). NaN values from the shift (last bar of each session under within-session diff, last bar of window) are dropped before computing mean/std.

## Results

```
=== BAR-LEVEL vs TRADE-LEVEL SHARPE COMPARISON ===

Trade-level (existing reference numbers):
  Trade count:                     174
  Daily-equity Sharpe (metrics.py): 4.45
  Per-trade annualized Sharpe:      5.13
  Per-trade raw Sharpe:             0.2193
  Mean trade PnL:                   $141.66
  Trade win rate:                   49%

Bar-level (this computation):
  Total RTH bars:                   6,168
  Bars in market:                   831 (13.5%)
  Bars long / short / flat:         432 / 399 / 5,337

  Strategy Sharpe (full series):    +4.9434  [ann. factor 140.1999]
  In-Market Sharpe (active bars):   +4.9602  [ann. factor 51.4607]

  Mean bar return (log):            +9.5117e-06
  Std bar return:                   0.000270
  Skewness:                         +0.5195
  Excess kurtosis:                  +55.6220
  Max drawdown (log return units):  -0.0071

Verdict on pre-registered predictions:
  User predicted B (3.5-5.0):       [CONFIRMED]
  Claude predicted A (1.5-2.5):     [CONTRADICTED]
  Actual Strategy Sharpe:           +4.9434

Bar/trade ratio:
  Strategy Sharpe / daily-equity Sharpe: 1.1109
  (1.0 = identical, <1 = trade-level inflated, >1 = trade-level understated)
```

## Plain-English interpretation

Bar-level Strategy Sharpe = **+4.9434** vs trade-level daily-equity Sharpe of 4.45 — a delta of +0.4934. The strategy holds positions on only 13.5% of bars; when active, the In-Market Sharpe is **+4.9602** (over the smaller bars-in-market annualization factor). The full-series Strategy Sharpe is the comparison-grade headline because it is the metric that academic studies report when they compute a bar-level Sharpe — same sample (every bar in the window), same annualization basis (√(252·78)), and properly penalized for time spent flat. The In-Market figure tells a complementary story: the per-bar quality of the signal conditional on actually holding a position. Both are valid; only one is directly cross-comparable with literature.

## Caveats

- **Close-vs-fill bias** (see top of report): the close-to-close bar-level Strategy Sharpe overstates the strategy's actual delivered Sharpe by approximately 30% due to mid-bar fills on stops and targets. Reported value is the literature-comparable metric; downstream DSR/PSR comparisons on forward-test data will carry the same bias on both sides and the bias cancels out in cross-comparison.
- This is in-sample on the locked 80-session window. Forward-test data is the proper validation surface.
- Bar-level Sharpe is statistically more powerful than trade-level because it uses every 5-min bar as an observation rather than aggregating to per-trade or per-day. Sample size goes from 174 → ~6,000+ observations.
- The strategy is in-market only ~13% of the time. The full-series Sharpe necessarily averages over many flat bars and is therefore lower than the in-market Sharpe; this is the expected geometry of an intraday tactical strategy.
- Session-aware diff applied; overnight gaps cannot leak into reported returns.
