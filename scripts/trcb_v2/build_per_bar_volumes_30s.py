"""TRCB-v2 — streaming MBP-10 pass for 30-second per-bar directional volumes.

THROWAWAY in-sample analysis. See common.CRITICAL_DISCLOSURE.

Mirrors trcb_filter/build_per_bar_volumes.py but with WINDOW_SECONDS=30.
Resume-safe: skips fully-processed session_dates in the output parquet.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (  # noqa: E402
    MBP10_DIR, OUTPUT_DIAG_DIR, PER_BAR_VOLUMES_PATH,
    TIMEZONE, WINDOW_SECONDS, classify_trades, rth_5min_bar_closes,
)

NEEDED_COLS = ["ts_event", "action", "side", "price", "size", "bid_px_00", "ask_px_00"]
DISAGREE_FLAG_THRESHOLD = 0.02


def process_day(parquet_path: Path) -> tuple[pd.DataFrame, dict]:
    raw = pd.read_parquet(parquet_path, columns=NEEDED_COLS)
    if not isinstance(raw["ts_event"].dtype, pd.DatetimeTZDtype):
        raw["ts_event"] = pd.to_datetime(raw["ts_event"], utc=True)
    trades = raw.loc[raw["action"] == "T"].copy()
    sess_date = pd.Timestamp(parquet_path.stem.replace("front_month_", "")).date()
    if trades.empty:
        return _empty_day(sess_date), {
            "session_date": sess_date, "n_trades": 0, "disagree_rate": 0.0,
            "n_bars": 0, "flagged": False,
        }

    trades = classify_trades(trades)
    n_trades_day = len(trades)
    disagree_rate = float(trades["side_disagrees"].sum()) / n_trades_day

    et_times = trades["ts_event"].dt.tz_convert(TIMEZONE)
    sess_dates = et_times.dt.date.unique()
    if len(sess_dates) == 1:
        sess_date = sess_dates[0]

    bar_closes_et = rth_5min_bar_closes(sess_date)
    bar_closes_utc = bar_closes_et.tz_convert("UTC")

    trades = trades.sort_values("ts_event")
    ts_arr = trades["ts_event"].values.astype("datetime64[ns]")
    size_arr = trades["size"].astype("int64").values
    is_buy_arr = trades["is_buy"].values
    is_sell_arr = trades["is_sell"].values
    locked_arr = trades["locked"].values

    rows = []
    for t_utc in bar_closes_utc:
        t_ns = np.datetime64(t_utc.tz_convert("UTC").tz_localize(None), "ns")
        end_ns = t_ns + np.timedelta64(WINDOW_SECONDS, "s")
        lo = np.searchsorted(ts_arr, t_ns, side="left")
        hi = np.searchsorted(ts_arr, end_ns, side="left")
        if hi <= lo:
            rows.append({
                "bar_close_utc": t_utc, "session_date": sess_date,
                "dir_buy_vol_30s": 0, "dir_sell_vol_30s": 0,
                "n_trades_30s": 0, "locked_spread_count": 0,
                "day_side_disagree_rate": disagree_rate,
            })
            continue
        sl_size = size_arr[lo:hi]
        sl_buy = is_buy_arr[lo:hi]
        sl_sell = is_sell_arr[lo:hi]
        sl_lock = locked_arr[lo:hi]
        rows.append({
            "bar_close_utc": t_utc, "session_date": sess_date,
            "dir_buy_vol_30s": int(sl_size[sl_buy].sum()),
            "dir_sell_vol_30s": int(sl_size[sl_sell].sum()),
            "n_trades_30s": int(hi - lo),
            "locked_spread_count": int(sl_lock.sum()),
            "day_side_disagree_rate": disagree_rate,
        })

    df = pd.DataFrame(rows)
    return df, {
        "session_date": sess_date, "n_trades": n_trades_day,
        "disagree_rate": disagree_rate, "n_bars": len(df),
        "flagged": disagree_rate > DISAGREE_FLAG_THRESHOLD,
    }


def _empty_day(sess_date) -> pd.DataFrame:
    bar_closes_et = rth_5min_bar_closes(sess_date)
    return pd.DataFrame({
        "bar_close_utc": bar_closes_et.tz_convert("UTC"),
        "session_date": [sess_date] * len(bar_closes_et),
        "dir_buy_vol_30s": 0, "dir_sell_vol_30s": 0,
        "n_trades_30s": 0, "locked_spread_count": 0,
        "day_side_disagree_rate": 0.0,
    })


def main() -> None:
    OUTPUT_DIAG_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(MBP10_DIR.glob("front_month_*.parquet"))
    print(f"TRCB-v2 (in-sample, throwaway): found {len(files)} MBP-10 day files")
    print(f"  WINDOW_SECONDS = {WINDOW_SECONDS}")

    existing = None
    completed_dates: set = set()
    if PER_BAR_VOLUMES_PATH.exists():
        existing = pd.read_parquet(PER_BAR_VOLUMES_PATH)
        completed_dates = set(pd.to_datetime(existing["session_date"]).dt.date.tolist())
        print(f"Resume: {len(completed_dates)} sessions already in {PER_BAR_VOLUMES_PATH.name}")

    new_dfs = []
    day_metrics_list = []
    t0 = time.time()
    for i, p in enumerate(files, 1):
        sess_str = p.stem.replace("front_month_", "")
        try:
            sess_date_candidate = pd.Timestamp(sess_str).date()
        except Exception:
            continue
        if sess_date_candidate in completed_dates:
            continue
        t_day = time.time()
        try:
            df_day, metrics = process_day(p)
        except Exception as e:
            print(f"  [ERR ] {p.name}: {e!r}")
            continue
        new_dfs.append(df_day)
        day_metrics_list.append(metrics)
        elapsed_day = time.time() - t_day
        flag = " ⚑ DISAGREE" if metrics["flagged"] else ""
        if i % 10 == 0 or i <= 3 or metrics["flagged"]:
            print(f"  [{i:>3d}/{len(files)}] {sess_str}  "
                  f"trades={metrics['n_trades']:>7,}  "
                  f"disagree={metrics['disagree_rate']*100:.3f}%  "
                  f"bars={metrics['n_bars']}  ({elapsed_day:.1f}s){flag}", flush=True)

    if new_dfs:
        new_concat = pd.concat(new_dfs, ignore_index=True)
        if existing is not None:
            full = pd.concat([existing, new_concat], ignore_index=True)
        else:
            full = new_concat
        full = full.drop_duplicates(subset=["bar_close_utc"], keep="last") \
                   .sort_values("bar_close_utc").reset_index(drop=True)
        full.to_parquet(PER_BAR_VOLUMES_PATH, index=False)
        print(f"\nSaved {PER_BAR_VOLUMES_PATH} — {len(full):,} bars across "
              f"{full['session_date'].nunique()} sessions")
    else:
        print("\nNo new days to process.")

    if day_metrics_list:
        n_flagged = sum(1 for m in day_metrics_list if m["flagged"])
        total_n = sum(m["n_trades"] for m in day_metrics_list)
        overall_disagree = (
            sum(m["disagree_rate"] * m["n_trades"] for m in day_metrics_list)
            / max(1, total_n)
        )
        print(f"\nDay-level disagreement: weighted mean = {overall_disagree*100:.4f}%, "
              f"flagged days = {n_flagged}")
        if n_flagged:
            for m in day_metrics_list:
                if m["flagged"]:
                    print(f"  flagged: {m['session_date']} rate={m['disagree_rate']*100:.3f}%")
    print(f"\nTotal wall-clock: {(time.time()-t0)/60:.1f} min")


if __name__ == "__main__":
    main()
