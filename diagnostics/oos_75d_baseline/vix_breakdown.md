# OOS VIX Bucket Breakdown

Total OOS trades after VIX join: 158
VIX range over OOS period: 13.47 - 26.42

## Per-bucket

bucket,n,win_rate,expectancy,total_pnl,per_trade_sharpe,is_n,is_sharpe,is_pnl
low,10,0.4,-85.0,-850.0,-0.3619,21,0.025,195.0
low_mid,102,0.4902,47.63,4858.75,0.0956,55,0.077,2131.0
mid,17,0.4706,137.65,2340.0,0.2368,29,0.034,486.0
elevated,23,0.5217,-107.17,-2465.0,-0.1468,40,0.574,18006.0
high,6,0.5,45.0,270.0,0.0511,29,0.158,3830.0


## Confound check (VIX 20-25 × 0DTE)

- VIX 20-25 × 0DTE: n=15, total=$-2,631.25
- VIX 20-25 × non-0DTE: n=8, total=$166.25

## Reading

**Pre-registration:** Rafa predicted E (VIX 20-25 still concentrates edge on OOS, independent of 0DTE).

**Result:** Prediction E is invalidated. VIX 20-25 bucket: in-sample Sharpe +0.574 ($18,006, 73% of IS PnL) → OOS Sharpe -0.147 (-$2,465). Pattern fully inverted.

**Confound check:** Both VIX 20-25 × 0DTE and VIX 20-25 × non-0DTE are negative or flat. Not a 0DTE proxy — VIX 20-25 just doesn't generalize.

**Pattern emerging across OOS diagnostics:** Two consecutive in-sample patterns (0DTE day-of-week, VIX 20-25 bucket) both inverted on OOS. The in-sample 80-day window had specific characteristics that don't extend backward to Sept-Dec 2025.

