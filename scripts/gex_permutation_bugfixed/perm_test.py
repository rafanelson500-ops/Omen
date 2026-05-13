"""Tier 5.3 GEX permutation test — RE-RUN on bugfixed infrastructure.

Uses the bugfixed features.py + backtest.py now on main. Methodology
matches the original `backend/scripts/gex_permutation_test_fast.py`
for the simple-shuffle arm. Adds a block-permutation arm (5-session
blocks) as a methodologically more rigorous variant that preserves
within-session timing AND short-range autocorrelation.

Window: 2025-09-08 → 2025-12-23 (same as original Tier 5.3 OOS window).
Locked params: z=1.8, blackout_lunch=True, stop=2.0×ATR, target=4.5×ATR,
time_stop=25min, ATR=14, bar_freq=5min.

Test statistic: Sharpe (primary) + profit factor + total PnL (secondary).
p-value = (#permuted >= real) / N (one-sided, observed-or-better).
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path("/Users/rafanelson/Omen")
sys.path.insert(0, str(REPO / "backend"))

from cheese import backtest, features, gex, market, metrics, strategy  # noqa: E402
from cheese.config import BacktestConfig  # noqa: E402

START = date(2025, 9, 8)
END = date(2025, 12, 23)
FREQ = "5min"
Z_THRESHOLD = 1.8
BLACKOUT_LUNCH = True
BLOCK_SIZE_SESSIONS = 5  # block-permutation default per spec

OUT_DIR = REPO / "analysis/gex-permutation-bugfixed"


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--n", type=int, default=500,
                    help="permutations per methodology (default 500)")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--method", type=str, choices=["simple", "block", "both"],
                    default="both")
    p.add_argument("--block-size", type=int, default=BLOCK_SIZE_SESSIONS,
                    help="block size in sessions for block-permutation")
    return p.parse_args()


def _precompute_session_bounds(gex_raw: pd.DataFrame) -> np.ndarray:
    session_dates = gex_raw.index.normalize().values
    is_new = np.concatenate([[True], session_dates[1:] != session_dates[:-1]])
    starts = np.where(is_new)[0]
    ends = np.concatenate([starts[1:], [len(gex_raw)]])
    return np.column_stack([starts, ends])


def _shuffle_within_session(gex_raw: pd.DataFrame, session_bounds: np.ndarray,
                              rng: np.random.Generator) -> pd.DataFrame:
    perm = np.arange(len(gex_raw))
    for start, end in session_bounds:
        rng.shuffle(perm[start:end])
    shuffled = gex_raw.iloc[perm].copy()
    shuffled.index = gex_raw.index
    return shuffled


def _block_permute_sessions(gex_raw: pd.DataFrame, session_bounds: np.ndarray,
                              block_size: int, rng: np.random.Generator) -> pd.DataFrame:
    """Shuffle blocks of `block_size` consecutive sessions.

    Preserves: within-session temporal order; intra-block alignment.
    Destroys: longer-range alignment between GEX patterns and market state.
    """
    n_sessions = len(session_bounds)
    n_blocks = (n_sessions + block_size - 1) // block_size
    block_ids = np.arange(n_blocks)
    rng.shuffle(block_ids)

    # Build permuted row index: for each block in the new order, concatenate
    # the row indices of the sessions in that block (in original within-block order).
    new_row_index_parts = []
    for nb in block_ids:
        sess_lo = nb * block_size
        sess_hi = min(sess_lo + block_size, n_sessions)
        for s in range(sess_lo, sess_hi):
            start, end = session_bounds[s]
            new_row_index_parts.append(np.arange(start, end))
    perm = np.concatenate(new_row_index_parts)
    shuffled = gex_raw.iloc[perm].copy()
    shuffled.index = gex_raw.index  # restore original timestamps
    return shuffled


def _run_single(mkt: pd.DataFrame, gex_raw: pd.DataFrame,
                 cfg: BacktestConfig, strat: strategy.FlowBurstStrategy) -> dict:
    gex_bars = gex.resample(gex_raw, freq=FREQ)
    feat = features.build_features(mkt, gex_bars)
    signals = strat.signals(feat)
    trades, equity = backtest.run(feat, signals, strategy_name="flow_burst", cfg=cfg)
    summ = metrics.summarize(trades, equity)
    n = len(trades)
    pnl = float(trades["net_dollars"].sum()) if n > 0 else 0.0
    wins = int((trades["net_dollars"] > 0).sum()) if n > 0 else 0
    losses = int((trades["net_dollars"] < 0).sum()) if n > 0 else 0
    avg_win = float(trades.loc[trades["net_dollars"] > 0, "net_dollars"].mean()) if wins > 0 else 0.0
    avg_loss = float(trades.loc[trades["net_dollars"] < 0, "net_dollars"].mean()) if losses > 0 else 0.0
    gross_profit = avg_win * wins if wins > 0 else 0.0
    gross_loss = abs(avg_loss * losses) if losses > 0 else 0.0
    pf = gross_profit / gross_loss if gross_loss > 0 else (999.0 if gross_profit > 0 else 0.0)
    return {"n_trades": n, "total_pnl": pnl, "profit_factor": pf,
             "win_rate": wins / n if n > 0 else 0.0,
             "sharpe": float(summ.get("sharpe_daily", 0.0))}


def main() -> int:
    args = _parse_args()
    rng = np.random.default_rng(args.seed)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 72)
    print("Tier 5.3 GEX permutation test — BUGFIXED RE-RUN")
    print("=" * 72)
    print(f"  Window      : {START} → {END}  @ {FREQ}")
    print(f"  Params      : z={Z_THRESHOLD}, blackout_lunch={BLACKOUT_LUNCH}")
    print(f"  Methods     : {args.method}  (block_size={args.block_size} sessions)")
    print(f"  Permutations: {args.n} per method  (seed={args.seed})")

    # Data
    print("\nLoading market + GEX ...")
    days = gex.rth_sessions(START, END)
    mkt = market.load(START, END, freq=FREQ, rth_only=True)
    gex_raw = gex.load_range(days)
    if gex_raw.empty:
        print("[FATAL] gex.load_range empty.")
        return 1
    print(f"  market bars: {len(mkt):,}  GEX rows: {len(gex_raw):,}  sessions: {len(days)}")
    session_bounds = _precompute_session_bounds(gex_raw)
    print(f"  session bounds: {len(session_bounds)} (block-perm will shuffle "
          f"{(len(session_bounds) + args.block_size - 1) // args.block_size} blocks)")

    cfg = BacktestConfig(bar_freq=FREQ)
    strat = strategy.FlowBurstStrategy(z_threshold=Z_THRESHOLD,
                                        blackout_lunch=BLACKOUT_LUNCH)

    # Real (unshuffled) baseline — uses bugfixed infrastructure
    print("\nReal (unshuffled, bugfixed) baseline ...")
    t0 = time.time()
    real = _run_single(mkt, gex_raw, cfg, strat)
    print(f"  real Sharpe: {real['sharpe']:+.4f}  PF: {real['profit_factor']:.4f}  "
          f"PnL: ${real['total_pnl']:+.2f}  trades: {real['n_trades']}  "
          f"({time.time()-t0:.1f}s)")

    results = {"real": real, "simple": None, "block": None}

    def _run_perms(method: str, n: int) -> list[dict]:
        out = []
        t0 = time.time()
        for i in range(n):
            if method == "simple":
                shuffled = _shuffle_within_session(gex_raw, session_bounds, rng)
            else:
                shuffled = _block_permute_sessions(gex_raw, session_bounds,
                                                     args.block_size, rng)
            r = _run_single(mkt, shuffled, cfg, strat)
            out.append(r)
            if (i + 1) % max(1, n // 10) == 0:
                elapsed = time.time() - t0
                eta = elapsed / (i + 1) * (n - i - 1)
                print(f"  [{method}] {i+1}/{n}  "
                      f"mean Sharpe={np.mean([x['sharpe'] for x in out]):+.3f}  "
                      f"({elapsed:.0f}s elapsed, ETA {eta:.0f}s)", flush=True)
        return out

    if args.method in ("simple", "both"):
        print(f"\nSimple shuffle (within-session row permutation), N={args.n} ...")
        results["simple"] = _run_perms("simple", args.n)
    if args.method in ("block", "both"):
        print(f"\nBlock permutation (block_size={args.block_size} sessions), N={args.n} ...")
        results["block"] = _run_perms("block", args.n)

    # Compute p-values + save
    print("\n" + "=" * 72)
    print("RESULTS")
    print("=" * 72)
    print(f"  Real Sharpe (bugfixed) : {real['sharpe']:+.4f}")
    print(f"  Real PF                : {real['profit_factor']:+.4f}")
    print(f"  Real PnL               : ${real['total_pnl']:+.2f}")

    summary_rows = []
    for label, perms in (("simple_shuffle", results["simple"]),
                          ("block_permutation", results["block"])):
        if perms is None:
            continue
        sh = np.array([r["sharpe"] for r in perms])
        pf = np.array([r["profit_factor"] for r in perms])
        pnl = np.array([r["total_pnl"] for r in perms])
        p_sh = float(np.mean(sh >= real["sharpe"]))
        p_pf = float(np.mean(pf >= real["profit_factor"]))
        p_pnl = float(np.mean(pnl >= real["total_pnl"]))
        print(f"\n--- {label} (N={len(perms)}) ---")
        print(f"  Sharpe : mean={sh.mean():+.4f}  median={np.median(sh):+.4f}  "
              f"q05={np.percentile(sh, 5):+.4f}  q95={np.percentile(sh, 95):+.4f}  "
              f"p={p_sh:.4f}")
        print(f"  PF     : mean={pf.mean():+.4f}  median={np.median(pf):+.4f}  "
              f"q05={np.percentile(pf, 5):+.4f}  q95={np.percentile(pf, 95):+.4f}  "
              f"p={p_pf:.4f}")
        print(f"  PnL    : mean=${pnl.mean():+.0f}  median=${np.median(pnl):+.0f}  "
              f"q05=${np.percentile(pnl, 5):+.0f}  q95=${np.percentile(pnl, 95):+.0f}  "
              f"p={p_pnl:.4f}")
        summary_rows.append({
            "method": label, "n_perms": len(perms),
            "p_sharpe": p_sh, "p_pf": p_pf, "p_pnl": p_pnl,
            "sharpe_mean": float(sh.mean()), "sharpe_median": float(np.median(sh)),
            "sharpe_q05": float(np.percentile(sh, 5)),
            "sharpe_q95": float(np.percentile(sh, 95)),
            "pf_mean": float(pf.mean()), "pf_median": float(np.median(pf)),
            "pf_q95": float(np.percentile(pf, 95)),
            "pnl_mean": float(pnl.mean()), "pnl_median": float(np.median(pnl)),
        })

    pd.DataFrame(summary_rows).to_csv(OUT_DIR / "perm_summary.csv", index=False)
    print(f"\nSaved: {OUT_DIR / 'perm_summary.csv'}")
    # Save raw perm distributions for synthesis to render
    if results["simple"] is not None:
        pd.DataFrame(results["simple"]).to_csv(OUT_DIR / "perm_dist_simple.csv", index=False)
    if results["block"] is not None:
        pd.DataFrame(results["block"]).to_csv(OUT_DIR / "perm_dist_block.csv", index=False)
    pd.DataFrame([real]).to_csv(OUT_DIR / "perm_real.csv", index=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
