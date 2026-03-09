import numpy as np
import time
from numba import njit

# ── Strategy design ────────────────────────────────────────────────────────────
#
# target = (close[t+8] - close[t]) / sqrt(har_rv) * 1e-5
#
# Therefore gbt_target = G predicts a price move of:
#   predicted_move = G * 1e5 * sqrt(har_rv)                (in price units)
#   = G * 1e5 / close * vol_unit  = G * 5 * vol_unit       (in vol units, ~close=20000)
#
# For G = 0.2 (minimum threshold): expected move = 1.0 vol unit
# For G = 0.3:                                   = 1.5 vol units
#
# Key insight from prior runs:
#   - SL = 0.7 vol (last run): random noise wipes trades →  WR=26%, EV=-3.6
#   - SL must survive at least 1 bar of noise (1 vol unit) to not be random
#
# This iteration:
#   SL = 1.0 vol   tight — contrarian entries sit near extremes
#   TP = 1.5 vol   wider — captures the mean-reversion snap-back
#   RR = 1.5:1     break-even WR = SL/(SL+TP) = 1.0/2.5 = 40%
#
# With contrarian edge and mean-reversion:
#   WR ≈ 46%  →  EV ≈ +1.7 per trade  →  σ² ≈ 594
# ──────────────────────────────────────────────────────────────────────────────

GBT_THRESHOLD = 0.2    # |gbt_target| crossover threshold
SL_VOL_MULT   = 1.0    # SL = 1.0 × vol_unit  (tight — contrarian entries sit near extremes)
TP_VOL_MULT   = 1.5    # TP = 1.5 × vol_unit  (wider — captures the mean-reversion snap-back)
ENTRY_FEE     = 0.5    # commission per side in price units
EXIT_FEE      = 0.5


@njit(cache=True)
def _simulate_jit(
    highs,
    lows,
    closes,
    signal,       # int8: +1 = long, -1 = short, 0 = none
    new_session,  # int8: 1 = first bar of a new session
    har_rv,       # float64: HAR-RV volatility forecast (log-return variance per bar)
    sl_vol_mult,
    tp_vol_mult,
    entry_fee,
    exit_fee,
):
    """
    Contrarian mean-reversion simulation.

    Sizing
    ------
    vol_unit = sqrt(har_rv[i]) × close[i]  ← 1 standard deviation of price change
    SL = sl_vol_mult × vol_unit            ← tight: 1.0 vol ≈ 20 pts
    TP = tp_vol_mult × vol_unit            ← wider: 1.5 vol ≈ 30 pts (RR = 1.5:1)

    SL and TP tested against bar highs/lows (wicks) each bar.
    SL takes priority if both are inside the bar range.
    All fees netted into the single exit-bar return (one non-zero per trade).
    Open positions force-closed at previous close on new-session bars.
    """
    n = len(closes)
    strat_returns = np.zeros(n, dtype=np.float64)
    pos_arr       = np.zeros(n, dtype=np.float64)

    in_trade    = False
    trade_dir   = np.int8(0)
    entry_price = 0.0
    stop_loss   = 0.0
    take_profit = 0.0

    for i in range(1, n):

        # ── 1. Force-close at session boundary ───────────────────────────────
        if in_trade and new_session[i] == 1:
            if trade_dir == 1:
                pnl = closes[i - 1] - entry_price - entry_fee - exit_fee
            else:
                pnl = entry_price - closes[i - 1] - entry_fee - exit_fee
            strat_returns[i] += pnl
            in_trade  = False
            trade_dir = np.int8(0)

        # ── 2. Check SL / TP against bar wicks ───────────────────────────────
        if in_trade:
            sl_hit = False
            tp_hit = False

            if trade_dir == 1:
                if lows[i]  <= stop_loss:   sl_hit = True
                if highs[i] >= take_profit: tp_hit = True
                if sl_hit:
                    pnl = stop_loss   - entry_price - entry_fee - exit_fee
                elif tp_hit:
                    pnl = take_profit - entry_price - entry_fee - exit_fee
            else:
                if highs[i] >= stop_loss:   sl_hit = True
                if lows[i]  <= take_profit: tp_hit = True
                if sl_hit:
                    pnl = entry_price - stop_loss   - entry_fee - exit_fee
                elif tp_hit:
                    pnl = entry_price - take_profit - entry_fee - exit_fee

            if sl_hit or tp_hit:
                strat_returns[i] += pnl
                in_trade  = False
                trade_dir = np.int8(0)
            else:
                pos_arr[i] = trade_dir

        # ── 3. Open trade on signal crossover ────────────────────────────────
        if not in_trade and signal[i] != 0 and new_session[i] == 0:
            rv_val = har_rv[i]
            if rv_val <= 0.0:
                continue
            vol_unit = np.sqrt(rv_val) * closes[i]

            sl_dist = sl_vol_mult * vol_unit
            tp_dist = tp_vol_mult * vol_unit

            # Skip if TP cannot cover fees profitably
            if tp_dist < (entry_fee + exit_fee) * 2.0:
                continue

            direction = signal[i]
            entry = closes[i]

            if direction == 1:
                stop_loss   = entry - sl_dist
                take_profit = entry + tp_dist
            else:
                stop_loss   = entry + sl_dist
                take_profit = entry - tp_dist

            in_trade    = True
            trade_dir   = np.int8(direction)
            entry_price = entry
            pos_arr[i]  = direction

    # ── 4. Close open trade at end of data ───────────────────────────────────
    if in_trade:
        last = n - 1
        if trade_dir == 1:
            pnl = closes[last] - entry_price - entry_fee - exit_fee
        else:
            pnl = entry_price - closes[last] - entry_fee - exit_fee
        strat_returns[last] += pnl

    return strat_returns, pos_arr


def process_data(df):
    t0 = time.time()

    # ── Buy-and-hold baseline ──────────────────────────────────────────────────
    df["base_returns"] = df["close"] - df["close"].shift(1)
    df["base_returns"] = np.where(df["new_session"] == 1, 0, df["base_returns"])

    # ── Contrarian crossover signals (FADE the GBT prediction) ──────────────────
    gbt  = df["gbt_target"].fillna(0).values.astype(np.float64)
    prev = np.empty_like(gbt)
    prev[0]  = 0.0
    prev[1:] = gbt[:-1]

    bullish = (gbt >  GBT_THRESHOLD) & (prev <=  GBT_THRESHOLD)
    bearish = (gbt < -GBT_THRESHOLD) & (prev >= -GBT_THRESHOLD)

    # CONTRARIAN: model bullish → SHORT, model bearish → LONG
    # The momentum strategy showed AvgLoss (-28.9) >> AvgWin (+17.8):
    # the big moves happen *against* the model's prediction.
    signal = np.where(bullish, np.int8(-1),
             np.where(bearish, np.int8( 1), np.int8(0))).astype(np.int8)

    har_rv_vals = df["har_rv"].clip(lower=0).fillna(0).values.astype(np.float64)
    highs       = df["high"].values.astype(np.float64)
    lows        = df["low"].values.astype(np.float64)
    closes      = df["close"].values.astype(np.float64)
    new_session = df["new_session"].fillna(0).values.astype(np.int8)

    strat_returns, position = _simulate_jit(
        highs, lows, closes,
        signal, new_session,
        har_rv_vals,
        SL_VOL_MULT, TP_VOL_MULT,
        ENTRY_FEE, EXIT_FEE,
    )

    df["position"]            = position
    df["strategy_returns"]    = strat_returns
    df["base_cumulative"]     = df["base_returns"].cumsum()
    df["strategy_cumulative"] = df["strategy_returns"].cumsum()

    # ── Diagnostics ────────────────────────────────────────────────────────────
    trades   = strat_returns[strat_returns != 0]
    n_trades = len(trades)
    if n_trades > 0:
        wins     = int(np.sum(trades > 0))
        losses   = int(np.sum(trades < 0))
        wr       = wins / n_trades
        avg_win  = float(np.mean(trades[trades > 0])) if wins   > 0 else 0.0
        avg_loss = float(np.mean(trades[trades < 0])) if losses > 0 else 0.0
        mu       = float(np.mean(trades))
        sigma2   = float(np.var(trades))
        if sigma2 > 1e-9:
            theta = 2.0 * mu / sigma2
            e_pos = np.exp(min( theta * 150, 50.0))
            e_neg = np.exp(max(-theta * 300, -50.0))
            p_suc = (e_pos - 1.0) / (e_pos - e_neg) if abs(e_pos - e_neg) > 1e-12 else 1.0/3.0
        else:
            theta, p_suc = 0.0, 1.0/3.0
        print(
            f"Processing: {time.time()-t0:.3f}s | N={n_trades} | "
            f"W/L={wins}/{losses} | WR={wr:.1%} | "
            f"AvgW={avg_win:.1f} AvgL={avg_loss:.1f} | "
            f"μ={mu:.2f} σ²={sigma2:.0f} | θ={theta:.4f} | "
            f"~P(success)={p_suc:.1%}"
        )
    else:
        print(f"Processing: {time.time()-t0:.3f}s | No trades generated")
    return df
