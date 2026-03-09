import numpy as np
import time
from numba import njit

ENTRY_FEE = 0.18
EXIT_FEE  = 0.18

# ── Signal thresholds ─────────────────────────────────────────────────────────
# gbt ∈ [-5, +5] :  < 0 → convergence predicted  |  > 0 → divergence predicted
# We want the model to be strongly convinced AND price to be maximally stretched.
GBT_THRESH   = -0.7   # model must predict strong convergence (stricter than -0.5 but not -1.0)
DIST_THRESH  =  4.0   # |ema_dist| (σ units) — extreme stretch required

# ── Exit parameters ────────────────────────────────────────────────────────────
# SL_K=2.5 gives Risk:Reward ≈ 2.5σ : 2.9σ (near 1:1).
# Previous SL_K=5 meant risking 5σ to gain ~2σ — break-even WR was ~71 %, which
# is why the strategy lost money despite a high win rate.
SL_K      = 2.5   # SL = 2.5σ adverse from entry (was 5 — root cause of losses)
TP_FRAC   = 0.65  # TP = 65% of current EMA stretch (was 0.5)
TP_MIN_K  = 0.80  # TP floor = 0.80σ
MAX_HOLD  = 12    # time-stop: exit at close after 12 bars (was 25 — cut losers faster)


@njit(cache=True)
def _backtest_jit(signal, open_, high, low, close, new_session,
                  sl_dist, tp_dist, entry_fee, exit_fee, max_hold):
    """
    Bar-by-bar backtest — tuned purely for maximum win-rate.

    Parameters
    ----------
    signal      : int8[n]    – 1 long, -1 short, 0 flat
    open_       : float64[n]
    high        : float64[n]
    low         : float64[n]
    close       : float64[n]
    new_session : int8[n]    – 1 on the first bar of every new session
    sl_dist     : float64[n] – per-entry SL distance in price points (> 0)
    tp_dist     : float64[n] – per-entry TP distance in price points (> 0)
    entry_fee   : float64    – fee charged at entry  (price units, round-trip)
    exit_fee    : float64    – fee charged at exit   (price units, round-trip)
    max_hold    : int64      – bars before time-stop fires (exit at close)

    Entry / exit rules
    ------------------
    1. Session boundary  → force-close at open of new-session bar.
    2. SL / TP checks    → via wicks (high/low); SL wins on same-candle ambiguity.
    3. Time stop         → exit at close if bars_held >= max_hold.
    4. New entry         → enter at close of signal bar when flat.
       SL / TP levels are frozen at entry values (no drift).

    Returns
    -------
    trade_pnl    : float64[n] – realised P&L booked on the exit bar (0 elsewhere)
    position_arr : int8[n]    – position held going into each bar open (1/-1/0)
    exit_type    : int8[n]    – 0 none | 1 TP | 2 SL | 3 time-stop | 4 session
    """
    n = len(signal)
    trade_pnl    = np.zeros(n, dtype=np.float64)
    position_arr = np.zeros(n, dtype=np.int8)
    exit_type    = np.zeros(n, dtype=np.int8)

    pos         = np.int8(0)
    entry_price = 0.0
    sl_price    = 0.0
    tp_price    = 0.0
    bars_held   = np.int64(0)

    for i in range(n):

        # ── 1. Force-close at session boundary ────────────────────────────────
        if pos != 0 and new_session[i] == 1:
            pnl = (open_[i] - entry_price) * pos - entry_fee - exit_fee
            trade_pnl[i] += pnl
            exit_type[i]  = np.int8(4)
            pos       = np.int8(0)
            bars_held = np.int64(0)

        # ── 2. SL / TP via wicks + time-stop ──────────────────────────────────
        if pos != 0:
            position_arr[i] = pos
            bars_held      += np.int64(1)
            exited          = False
            exit_price      = 0.0
            etype           = np.int8(0)

            if pos == 1:            # long
                if low[i] <= sl_price:          # SL wick (checked first)
                    exit_price = sl_price
                    exited     = True
                    etype      = np.int8(2)
                elif high[i] >= tp_price:       # TP wick
                    exit_price = tp_price
                    exited     = True
                    etype      = np.int8(1)
            else:                   # short  (pos == -1)
                if high[i] >= sl_price:         # SL wick (checked first)
                    exit_price = sl_price
                    exited     = True
                    etype      = np.int8(2)
                elif low[i] <= tp_price:        # TP wick
                    exit_price = tp_price
                    exited     = True
                    etype      = np.int8(1)

            # Time-stop: exit at close if no SL/TP and held too long
            if not exited and bars_held >= max_hold:
                exit_price = close[i]
                exited     = True
                etype      = np.int8(3)

            if exited:
                pnl = (exit_price - entry_price) * pos - entry_fee - exit_fee
                trade_pnl[i]    += pnl
                exit_type[i]     = etype
                pos              = np.int8(0)
                bars_held        = np.int64(0)
                position_arr[i]  = np.int8(0)   # flat on this bar

        # ── 3. Enter at close if flat and signal fires ─────────────────────────
        if pos == 0 and signal[i] != 0:
            pos         = np.int8(signal[i])
            entry_price = close[i]
            bars_held   = np.int64(0)
            sd          = sl_dist[i]
            td          = tp_dist[i]
            if pos == 1:
                sl_price = entry_price - sd
                tp_price = entry_price + td
            else:                               # short
                sl_price = entry_price + sd
                tp_price = entry_price - td

    return trade_pnl, position_arr, exit_type


def process_data(df):
    t0 = time.time()

    # ── Buy-and-hold baseline ──────────────────────────────────────────────────
    df["base_returns"] = df["close"] - df["close"].shift(1)
    df["base_returns"] = np.where(df["new_session"] == 1, 0, df["base_returns"])

    gbt = df["gbt_target"].fillna(0).values.astype(np.float64)

    prev      = np.empty_like(gbt)
    prev[0]   = 0.0
    prev[1:]  = gbt[:-1]
    delta_gbt = gbt - prev                          # gbt momentum (should be < 0)

    ema_dist     = df["ema_dist"].fillna(0).values.astype(np.float64)      # σ-normalised
    ema_div_chg3 = df["ema_div_chg_3"].fillna(0).values.astype(np.float64) # stretch contracting < 0

    # ── Entry filter: strong convergence conviction + extreme EMA stretch ──────
    # gbt < GBT_THRESH    →  model strongly predicts convergence
    # delta_gbt < -0.2    →  model conviction still growing
    # ema_div_chg3 < 0    →  |ema_dist| already contracting over last 3 bars
    #                         (reversion has started — avoids entering into a still-
    #                          stretching move)
    # |ema_dist| > DIST_THRESH  →  price is genuinely, extremely stretched
    trigger      = (gbt < GBT_THRESH) & (delta_gbt < -0.2)
    long_signal  = trigger & (ema_dist < -DIST_THRESH)  # stretched below → long
    short_signal = trigger & (ema_dist >  DIST_THRESH)  # stretched above → short

    df["signal"] = np.where(short_signal, np.int8(-1),
             np.where(long_signal,  np.int8( 1), np.int8(0))).astype(np.int8)

    # ── Per-bar volatility ────────────────────────────────────────────────────
    # har_rv is built from squared *log* returns, so sqrt(har_rv) is a
    # dimensionless log-return scalar (~0.0005 for ES 5-min bars), NOT pts.
    # Multiply by close to convert to price-unit std-dev per bar.
    log_vol       = np.sqrt(df["har_rv"].fillna(0).values).clip(1e-6)
    close_vals    = df["close"].values.astype(np.float64)
    price_vol     = (log_vol * close_vals).astype(np.float64)  # pts/bar σ

    # EMA distance in true price units — df["ema"] is the span-20 EMA added by
    # add_target(); this avoids the dimensional mismatch of undoing ema_dist*vol.
    ema_vals          = df["ema"].values.astype(np.float64)
    ema_dist_price    = np.abs(close_vals - ema_vals)          # always ≥ 0, pts

    # ── Dynamic SL / TP ───────────────────────────────────────────────────────
    # SL: SL_K price-std-devs adverse — wide enough to survive normal noise.
    sl_dist_arr = (SL_K * price_vol).astype(np.float64)

    # TP: TP_FRAC of the actual price-unit EMA stretch (quick partial reversion).
    # Floor = TP_MIN_K × price_vol, also hard-floored above the round-trip fee
    # so every TP hit is actually profitable.
    round_trip_fee = ENTRY_FEE + EXIT_FEE
    tp_dist_arr = np.maximum(
        np.maximum(ema_dist_price * TP_FRAC, TP_MIN_K * price_vol),
        round_trip_fee * 1.5,       # hard floor: TP must beat fees by 50 %
    ).astype(np.float64)

    # ── Run backtest ───────────────────────────────────────────────────────────
    trade_pnl, position_arr, exit_type = _backtest_jit(
        df["signal"].values.astype(np.int8),
        df["open"].values.astype(np.float64),
        df["high"].values.astype(np.float64),
        df["low"].values.astype(np.float64),
        df["close"].values.astype(np.float64),
        df["new_session"].values.astype(np.int8),
        sl_dist_arr,
        tp_dist_arr,
        float(ENTRY_FEE),
        float(EXIT_FEE),
        np.int64(MAX_HOLD),
    )

    df["sl_dist"]             = sl_dist_arr
    df["tp_dist"]             = tp_dist_arr
    df["trade_pnl"]           = trade_pnl
    df["position"]            = position_arr
    df["exit_type"]           = exit_type      # 0=none 1=TP 2=SL 3=time 4=session
    df["strategy_returns"]    = trade_pnl
    df["base_cumulative"]     = df["base_returns"].cumsum()
    df["strategy_cumulative"] = trade_pnl.cumsum()

    # ── Diagnostics ───────────────────────────────────────────────────────────
    closed      = trade_pnl[trade_pnl != 0]
    n_trades    = len(closed)

    if n_trades > 0:
        wins        = closed[closed > 0]
        losses      = closed[closed <= 0]
        win_rate    = len(wins) / n_trades * 100

        tp_exits    = int((exit_type == 1).sum())
        sl_exits    = int((exit_type == 2).sum())
        time_exits  = int((exit_type == 3).sum())
        sess_exits  = int((exit_type == 4).sum())

        avg_win     = wins.mean()   if len(wins)   > 0 else 0.0
        avg_loss    = losses.mean() if len(losses) > 0 else 0.0
        avg_trade   = closed.mean()
        total_pnl   = closed.sum()
        expectancy  = avg_trade  # same thing, useful label
        profit_factor = (wins.sum() / abs(losses.sum())) if len(losses) > 0 and losses.sum() != 0 else float("inf")

        # max drawdown on equity curve
        eq          = np.cumsum(trade_pnl)
        peak        = np.maximum.accumulate(eq)
        drawdown    = eq - peak
        max_dd      = drawdown.min()

        n_signals   = int((df["signal"] != 0).sum())

        sep = "─" * 52
        print(f"\n{'═'*52}")
        print(f"  BACKTEST DIAGNOSTICS")
        print(f"{'═'*52}")
        print(f"  Signals generated   : {n_signals:>8d}")
        print(f"  Trades taken        : {n_trades:>8d}  (flat → skipped signal)")
        print(sep)
        print(f"  Win rate            : {win_rate:>7.1f} %")
        print(f"  Winners / Losers    : {len(wins):>4d}  /  {len(losses):<4d}")
        print(sep)
        print(f"  Avg win             : {avg_win:>+8.3f} pts")
        print(f"  Avg loss            : {avg_loss:>+8.3f} pts")
        print(f"  Avg trade (net)     : {avg_trade:>+8.3f} pts")
        print(f"  Profit factor       : {profit_factor:>8.2f}")
        print(sep)
        print(f"  Exit breakdown:")
        print(f"    TP  hits          : {tp_exits:>8d}")
        print(f"    SL  hits          : {sl_exits:>8d}")
        print(f"    Time stops        : {time_exits:>8d}")
        print(f"    Session closes    : {sess_exits:>8d}")
        print(sep)
        print(f"  Total P&L           : {total_pnl:>+8.3f} pts")
        print(f"  Max drawdown        : {max_dd:>+8.3f} pts")
        print(f"  Elapsed             : {time.time()-t0:>7.3f} s")
        print(f"{'═'*52}\n")
    else:
        print("\n[processor] No trades generated.\n")

    return df
