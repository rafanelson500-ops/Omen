"""Microprice continuation-confirmation early-exit overlay (EXPLORATORY).

THROWAWAY IN-SAMPLE ANALYSIS. See DISCLOSURE in synthesis. Cannot
validate the microprice concept — only filters whether it's worth a
fresh-data pre-registration.

Methodology
-----------
For each OMEN trade (bugfixed IS+OOS, 504 trades):
  1. Load the MBP-10 cache for the trade's session date.
  2. Take all top-of-book rows (any action) in the holding window
     [entry_time, original_exit_time], compute microprice per row.
  3. Build a 1-second grid via forward-fill of the most-recent
     microprice.
  4. Adverse condition (long): microprice ≤ entry_price − 0.50.
     Adverse condition (short): microprice ≥ entry_price + 0.50.
  5. Persistence: adverse must hold for 60 consecutive seconds.
  6. If persistence triggers BEFORE the original exit time, fire a
     microprice exit at that second. Exit price = best bid − 0.5×tick
     (long) or best ask + 0.5×tick (short), at the firing second.
     Cost dollars: same as the original trade.
  7. If microprice never triggers, the original exit + P&L stand.

Locked parameters (from first principles, no tuning):
  - Stoikov microprice = (bid_sz·ask_px + ask_sz·bid_px) / (bid_sz + ask_sz)
  - Adverse threshold: 2 ticks (0.50 ES points)
  - Persistence: 60 seconds continuous
  - Slippage on microprice exit: 0.5 tick adverse (same as time-stop)
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

REPO = Path("/Users/rafanelson/Omen")
MBP10_DIR = Path("/Users/rafanelson/Library/Caches/omen-pipeline-synthesis/mbp10_cache")
IS_BUGFIX = REPO / "diagnostics/all-bugfixes-baseline/is_all_bugfixes.csv"
OOS_BUGFIX = REPO / "diagnostics/all-bugfixes-baseline/oos_all_bugfixes.csv"
OUT_DIR = REPO / "analysis/microprice-continuation"
OUT_CSV = OUT_DIR / "microprice_overlay_results.csv"

ET = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")
TICK = 0.25
ADVERSE_TICKS = 2
ADVERSE_PTS = ADVERSE_TICKS * TICK    # 0.50 points
PERSIST_SEC = 60
SLIP_TICKS_PER_SIDE = 0.5
ES_POINT_VALUE = 50.0


def _load_trades() -> pd.DataFrame:
    is_df = pd.read_csv(IS_BUGFIX); is_df["sample"] = "IS"
    oos_df = pd.read_csv(OOS_BUGFIX); oos_df["sample"] = "OOS"
    df = pd.concat([is_df, oos_df], ignore_index=True)
    df["entry_time"] = pd.to_datetime(df["entry_time"], utc=True)
    df["exit_time"] = pd.to_datetime(df["exit_time"], utc=True)
    df["entry_time_et"] = df["entry_time"].dt.tz_convert(ET)
    df["exit_time_et"] = df["exit_time"].dt.tz_convert(ET)
    df["entry_date"] = df["entry_time_et"].dt.date
    df["side_label"] = np.where(df["side"] == 1, "LONG", "SHORT")
    df["cell"] = df["side_label"] + "_" + df["gamma_regime"].astype(str)
    return df.sort_values("entry_time").reset_index(drop=True)


def _load_session_book(session_date: dt.date) -> pd.DataFrame | None:
    """Top-of-book microprice frame for one session date, indexed UTC.

    Returns df with columns: bid_px, ask_px, bid_sz, ask_sz, microprice.
    """
    p = MBP10_DIR / f"front_month_{session_date.isoformat()}.parquet"
    if not p.exists():
        return None
    df = pd.read_parquet(p, columns=["bid_px_00", "ask_px_00",
                                       "bid_sz_00", "ask_sz_00"])
    # ts_recv is the parquet index, tz-aware UTC
    df.columns = ["bid_px", "ask_px", "bid_sz", "ask_sz"]
    # Microprice (Stoikov): weighted by opposite-side size
    denom = (df["bid_sz"] + df["ask_sz"]).astype(float)
    denom = denom.where(denom > 0, np.nan)
    df["microprice"] = (df["bid_sz"] * df["ask_px"]
                         + df["ask_sz"] * df["bid_px"]) / denom
    # Drop rows where microprice is undefined (zero size on both sides)
    df = df.dropna(subset=["microprice"])
    return df


def _persistence_check(times_sec: np.ndarray, microprice: np.ndarray,
                        side: int, entry_price: float,
                        persist_sec: int = PERSIST_SEC) -> int | None:
    """Return the index of the second where 60-sec adverse persistence completes.

    times_sec : seconds-from-entry on a 1-sec grid (monotonic).
    microprice: 1-sec forward-filled microprice values.
    side      : +1 long, -1 short.
    Returns the *array index* of the persistence-trigger second, or None.
    """
    if side == 1:
        adverse = microprice <= (entry_price - ADVERSE_PTS)
    else:
        adverse = microprice >= (entry_price + ADVERSE_PTS)
    if not adverse.any():
        return None
    run = 0
    for i in range(len(adverse)):
        if adverse[i]:
            run += 1
            if run >= persist_sec:
                return i
        else:
            run = 0
    return None


def _evaluate_trade(trade: pd.Series, book: pd.DataFrame) -> dict:
    """Return a dict with the microprice-overlay outcome for one trade."""
    entry_utc = trade["entry_time"]
    exit_utc = trade["exit_time"]
    side = int(trade["side"])
    entry_px = float(trade["entry_px"])

    # Slice book to the trade's holding window: [entry, exit].
    win = book.loc[(book.index >= entry_utc) & (book.index <= exit_utc),
                    ["bid_px", "ask_px", "microprice"]]
    if win.empty:
        # No book ticks during the window — overlay can't evaluate.
        return {"microprice_evaluable": False, "microprice_fired": False,
                "microprice_exit_time": pd.NaT, "microprice_exit_px": np.nan,
                "microprice_net": np.nan, "n_book_rows_in_window": 0}

    # Build a 1-second grid from entry_utc → exit_utc (inclusive).
    total_sec = int((exit_utc - entry_utc).total_seconds())
    if total_sec < PERSIST_SEC:
        # Window is shorter than persistence requirement — can't fire.
        return {"microprice_evaluable": True, "microprice_fired": False,
                "microprice_exit_time": pd.NaT, "microprice_exit_px": np.nan,
                "microprice_net": np.nan,
                "n_book_rows_in_window": int(len(win))}

    grid = pd.date_range(entry_utc.floor("s"),
                          entry_utc.floor("s") + pd.Timedelta(seconds=total_sec),
                          freq="1s")
    # Dedupe duplicate ts_recv timestamps (MBP-10 has multi-row events at the
    # same nanosecond: trade + cancel + add). Keep the last row at each ts.
    win_sorted = win.sort_index()
    win_sorted = win_sorted[~win_sorted.index.duplicated(keep="last")]
    grid_aligned = win_sorted.reindex(grid, method="ffill")
    # Drop the leading rows where no book data yet exists
    grid_aligned = grid_aligned.dropna(subset=["microprice"])
    if len(grid_aligned) < PERSIST_SEC:
        return {"microprice_evaluable": True, "microprice_fired": False,
                "microprice_exit_time": pd.NaT, "microprice_exit_px": np.nan,
                "microprice_net": np.nan,
                "n_book_rows_in_window": int(len(win))}

    times_sec = ((grid_aligned.index - entry_utc).total_seconds()).to_numpy()
    mp = grid_aligned["microprice"].to_numpy()
    fire_idx = _persistence_check(times_sec, mp, side, entry_px)

    if fire_idx is None:
        return {"microprice_evaluable": True, "microprice_fired": False,
                "microprice_exit_time": pd.NaT, "microprice_exit_px": np.nan,
                "microprice_net": np.nan,
                "n_book_rows_in_window": int(len(win))}

    fire_time = grid_aligned.index[fire_idx]
    bid = float(grid_aligned["bid_px"].iloc[fire_idx])
    ask = float(grid_aligned["ask_px"].iloc[fire_idx])
    # Exit fill: sell at bid - 0.5 tick (long), buy at ask + 0.5 tick (short)
    slip = SLIP_TICKS_PER_SIDE * TICK
    if side == 1:
        exit_px = bid - slip
    else:
        exit_px = ask + slip
    # Net P&L using the same cost_dollars as the original trade
    gross_pts = (exit_px - entry_px) * side
    gross_dollars = gross_pts * ES_POINT_VALUE * int(trade["contracts"])
    cost_dollars = float(trade["cost_dollars"])
    net = gross_dollars - cost_dollars
    return {"microprice_evaluable": True, "microprice_fired": True,
             "microprice_exit_time": fire_time,
             "microprice_exit_px": exit_px,
             "microprice_net": net,
             "n_book_rows_in_window": int(len(win))}


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print("=" * 72)
    print("Microprice continuation overlay (EXPLORATORY, IN-SAMPLE)")
    print("=" * 72)

    trades = _load_trades()
    print(f"  trades loaded: {len(trades)} "
          f"(IS={int((trades['sample']=='IS').sum())}, "
          f"OOS={int((trades['sample']=='OOS').sum())})")

    # Process by session-date to amortize I/O
    by_date: dict[dt.date, list[int]] = {}
    for i, r in trades.iterrows():
        by_date.setdefault(r["entry_date"], []).append(i)
    print(f"  unique session-dates: {len(by_date)}")

    results = []
    n_no_book = 0
    n_short_window = 0
    n_no_book_in_window = 0
    n_fired = 0
    n_processed = 0
    for d in sorted(by_date.keys()):
        idxs = by_date[d]
        book = _load_session_book(d)
        if book is None:
            n_no_book += len(idxs)
            for i in idxs:
                results.append({"trade_idx": i,
                                 "microprice_evaluable": False,
                                 "microprice_fired": False,
                                 "microprice_exit_time": pd.NaT,
                                 "microprice_exit_px": np.nan,
                                 "microprice_net": np.nan,
                                 "n_book_rows_in_window": 0})
            continue
        for i in idxs:
            r = _evaluate_trade(trades.iloc[i], book)
            r["trade_idx"] = i
            results.append(r)
            if r["microprice_fired"]:
                n_fired += 1
            elif r["n_book_rows_in_window"] == 0:
                n_no_book_in_window += 1
            elif not r["microprice_evaluable"]:
                n_short_window += 1
            n_processed += 1
        if (n_processed > 0
            and (sorted(by_date.keys()).index(d) + 1) % 10 == 0):
            print(f"  processed {sorted(by_date.keys()).index(d)+1}/{len(by_date)} sessions, "
                  f"trades={n_processed}, fired={n_fired}", flush=True)

    overlay = pd.DataFrame(results).set_index("trade_idx").sort_index()
    print(f"\n  trades evaluated         : {n_processed}")
    print(f"  trades with no book file : {n_no_book}")
    print(f"  trades with no book ticks: {n_no_book_in_window}")
    print(f"  trades with short window : {n_short_window}")
    print(f"  microprice fired         : {n_fired} "
          f"({100.0*n_fired/max(len(trades),1):.1f}% of all)")

    fire_rate = n_fired / max(len(trades), 1)
    if fire_rate < 0.01:
        print(f"\n  [WARN] Fire rate <1%. Verify implementation before interpreting results.")
    if fire_rate > 0.99:
        print(f"\n  [WARN] Fire rate >99%. Verify implementation before interpreting results.")

    # Merge overlay results onto trades
    out = trades.copy()
    for col in ("microprice_evaluable", "microprice_fired",
                 "microprice_exit_time", "microprice_exit_px",
                 "microprice_net", "n_book_rows_in_window"):
        out[col] = overlay[col].reindex(out.index)

    # Final arm-3 P&L: microprice net if fired, else original net
    out["arm3_net_dollars"] = np.where(out["microprice_fired"],
                                         out["microprice_net"],
                                         out["net_dollars"])
    out["arm3_exit_reason"] = np.where(out["microprice_fired"],
                                         "microprice", out["exit_reason"])

    keep_cols = [
        "sample", "side", "side_label", "cell", "gamma_regime",
        "entry_time", "exit_time", "entry_px", "exit_px",
        "atr_at_entry", "exit_reason", "bars_held",
        "gross_points", "gross_dollars", "cost_dollars", "net_dollars",
        "microprice_evaluable", "microprice_fired",
        "microprice_exit_time", "microprice_exit_px", "microprice_net",
        "n_book_rows_in_window",
        "arm3_net_dollars", "arm3_exit_reason",
    ]
    out[keep_cols].to_csv(OUT_CSV, index=False)
    print(f"\nSaved: {OUT_CSV}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
