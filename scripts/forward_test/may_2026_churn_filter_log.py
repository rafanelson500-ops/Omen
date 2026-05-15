"""Forward-test observational log: May 2026 OMEN trades joined to
OneMinL2 churn values, with high-churn filter counterfactual.

Locked threshold: 313.5333 e/s (IS median, do not retune).

Inputs (read-only):
  - backend/data/market/ES_c_0_ohlcv1s_*.parquet  (ES 1s OHLCV)
  - backend/data/gex/2026-05-*.parquet            (GEX snapshots)
  - /Users/rafanelson/OneMinL2/data/corpus_1min.parquet (churn)

Output: forward_test/may_2026_churn_filter_log.md
"""
from __future__ import annotations

import datetime as dt
import sys
from datetime import time
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

REPO = Path("/Users/rafanelson/Omen")
sys.path.insert(0, str(REPO / "backend"))

from cheese import backtest, features, gex, strategy  # noqa: E402
from cheese.config import BacktestConfig  # noqa: E402

ET = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")

OUT_PATH = REPO / "forward_test" / "may_2026_churn_filter_log.md"
OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

CHURN_PARQUET = Path("/Users/rafanelson/OneMinL2/data/corpus_1min.parquet")
CHURN_THRESHOLD = 313.5333  # IS-median, LOCKED

# Locked OMEN baseline
Z_THRESHOLD = 1.8
BAR_FREQ = "5min"
BLACKOUT_LUNCH = True
TIME_STOP_MIN = 25  # for duration sanity

MAY_DATES_TARGET = [
    dt.date(2026, 5, 1), dt.date(2026, 5, 4), dt.date(2026, 5, 5),
    dt.date(2026, 5, 6), dt.date(2026, 5, 7), dt.date(2026, 5, 8),
    dt.date(2026, 5, 11), dt.date(2026, 5, 12), dt.date(2026, 5, 13),
    dt.date(2026, 5, 14),
]

ES_FILES = [
    REPO / "backend/data/market/ES_c_0_ohlcv1s_2025-09-08_2026-04-27.parquet",
    REPO / "backend/data/market/ES_c_0_ohlcv1s_2026-04-28_2026-05-11.parquet",
    REPO / "backend/data/market/ES_c_0_ohlcv1s_2026-05-12_2026-05-12.parquet",
    REPO / "backend/data/market/ES_c_0_ohlcv1s_2026-05-13_2026-05-13.parquet",
    REPO / "backend/data/market/ES_c_0_ohlcv1s_2026-05-14_2026-05-14.parquet",
]

GEX_DIR = REPO / "backend" / "data" / "gex"


def _availability() -> tuple[list[dt.date], dict[dt.date, dict[str, bool]]]:
    """For each candidate date, mark whether ES bars and GEX snapshot exist.

    ES coverage is derived from file-name ranges (each cache is named
    ES_c_0_ohlcv1s_<start>_<end>.parquet), so we never have to read the
    parquet bodies just to decide availability.
    """
    avail = {}
    file_ranges: list[tuple[dt.date, dt.date]] = []
    for f in ES_FILES:
        if not f.exists():
            continue
        try:
            parts = f.stem.split("_")
            file_ranges.append((dt.date.fromisoformat(parts[-2]),
                                dt.date.fromisoformat(parts[-1])))
        except ValueError:
            continue
    def _es_covers(d: dt.date) -> bool:
        return any(s <= d <= e for s, e in file_ranges)
    for d in MAY_DATES_TARGET:
        gex_path = GEX_DIR / f"{d.isoformat()}.parquet"
        avail[d] = {
            "es": _es_covers(d),
            "gex": gex_path.exists(),
        }
    return MAY_DATES_TARGET, avail


def _es_file_for_date(d: dt.date) -> Path:
    """Pick the smallest cache file that contains `d`."""
    candidates: list[tuple[int, Path]] = []
    for f in ES_FILES:
        if not f.exists():
            continue
        try:
            parts = f.stem.split("_")
            f_start = dt.date.fromisoformat(parts[-2])
            f_end = dt.date.fromisoformat(parts[-1])
        except ValueError:
            continue
        if f_start <= d <= f_end:
            span = (f_end - f_start).days
            candidates.append((span, f))
    if not candidates:
        raise FileNotFoundError(f"no ES file covers {d}")
    candidates.sort()
    return candidates[0][1]


def _load_es(dates: list[dt.date]) -> pd.DataFrame:
    keep_dates = set(dates)
    files = sorted({_es_file_for_date(d) for d in dates})
    parts = [pd.read_parquet(p) for p in files]
    df = pd.concat(parts) if len(parts) > 1 else parts[0]
    df = df[~df.index.duplicated(keep="first")]
    df.index = pd.to_datetime(df.index, utc=True).tz_convert(ET)
    df = df.sort_index()
    df = df[df.index.normalize().map(lambda x: x.date() in keep_dates)]
    t = df.index.time
    df = df[(t >= time(9, 30)) & (t < time(16, 0))]
    df = (df.resample(BAR_FREQ, label="right", closed="right")
            .agg({"open": "first", "high": "max", "low": "min",
                   "close": "last", "volume": "sum"})
            .dropna(subset=["close"]))
    t = df.index.time
    df = df[(t > time(9, 30)) & (t <= time(16, 0))]
    return df


def _run_omen(dates: list[dt.date]) -> pd.DataFrame:
    # Run each session independently — matches the 2026-05-14 single-session
    # cell-breakdown convention and avoids cross-session signal-to-entry
    # leakage in the backtest loop (which iterates the feature frame without
    # session breaks at the signal level).
    strat = strategy.FlowBurstStrategy(z_threshold=Z_THRESHOLD,
                                       blackout_lunch=BLACKOUT_LUNCH)
    cfg = BacktestConfig(bar_freq=BAR_FREQ)
    chunks: list[pd.DataFrame] = []
    for d in dates:
        mkt = _load_es([d])
        gex_raw = gex.load_range([d])
        gex_bars = gex.resample(gex_raw, freq=BAR_FREQ)
        feat = features.build_features(mkt, gex_bars)
        signals = strat.signals(feat)
        t_df, _eq = backtest.run(feat, signals,
                                 strategy_name="flow_burst", cfg=cfg)
        if not t_df.empty:
            chunks.append(t_df)
    if not chunks:
        return pd.DataFrame()
    trades = pd.concat(chunks, ignore_index=True)
    if trades.empty:
        return trades
    trades = trades.copy()
    trades["entry_time"] = pd.to_datetime(trades["entry_time"], utc=True)
    trades["exit_time"] = pd.to_datetime(trades["exit_time"], utc=True)
    trades["entry_time_et"] = trades["entry_time"].dt.tz_convert(ET)
    trades["exit_time_et"] = trades["exit_time"].dt.tz_convert(ET)
    trades["date"] = trades["entry_time_et"].dt.date
    trades["direction"] = np.where(trades["side"] == 1, "LONG", "SHORT")
    trades["cell_label"] = trades["direction"] + "_" + trades["gamma_regime"].astype(str)
    trades["duration_min"] = (
        (trades["exit_time"] - trades["entry_time"]).dt.total_seconds() / 60.0
    )
    return trades


def _churn_lookup(corpus: pd.DataFrame, signal_ts_utc: pd.Timestamp,
                  fallback_ts_utc: pd.Timestamp) -> tuple[float, bool, bool]:
    """Return (churn, used_fallback, corpus_gap).

    Primary: 1-min bar with ts_open == signal_ts_utc.
    Fallback (only when signal_ts at 09:25 ET is pre-RTH): 1-min bar with
    ts_open == fallback_ts_utc (the 09:30 ET bar).
    """
    hit = corpus.loc[corpus["ts_open"] == signal_ts_utc, "churn"]
    if len(hit) >= 1:
        return float(hit.iloc[0]), False, False
    if signal_ts_utc.date() not in set(corpus["ts_open"].dt.date):
        return float("nan"), False, True
    hit_fb = corpus.loc[corpus["ts_open"] == fallback_ts_utc, "churn"]
    if len(hit_fb) >= 1:
        return float(hit_fb.iloc[0]), True, False
    return float("nan"), False, False


def _join_churn(trades: pd.DataFrame) -> tuple[pd.DataFrame, set[dt.date]]:
    if trades.empty:
        return trades, set()
    corpus = pd.read_parquet(CHURN_PARQUET)
    corpus["ts_open"] = pd.to_datetime(corpus["ts_open"], utc=True)
    corpus_dates = set(corpus["ts_open"].dt.date)
    churns, used_fb, opening_bar_flag = [], [], []
    for _, row in trades.iterrows():
        entry_et = row["entry_time_et"]
        signal_et = entry_et - pd.Timedelta(minutes=5)
        opening = (entry_et.time() == time(9, 30))
        opening_bar_flag.append(opening)
        if opening:
            sig_ts_utc = pd.Timestamp(entry_et).tz_convert(UTC)
            fb_ts_utc = sig_ts_utc
        else:
            sig_ts_utc = pd.Timestamp(signal_et).tz_convert(UTC)
            fb_ts_utc = pd.Timestamp(entry_et).tz_convert(UTC)
        ch, _fb, gap = _churn_lookup(corpus, sig_ts_utc, fb_ts_utc)
        churns.append(ch)
        used_fb.append(opening)  # only opening trades use the special bar
    out = trades.copy()
    out["churn_at_signal"] = churns
    out["opening_bar_fallback"] = opening_bar_flag
    out["corpus_gap"] = [d not in corpus_dates for d in out["date"]]
    return out, corpus_dates


def _bucket(row) -> str:
    if pd.isna(row["churn_at_signal"]):
        return "NaN"
    return "HIGH" if row["churn_at_signal"] >= CHURN_THRESHOLD else "LOW"


def _stats(net: pd.Series) -> dict:
    n = len(net)
    if n == 0:
        return {"n": 0, "total": 0.0, "mean": 0.0, "win_rate": None,
                "avg_win": None, "avg_loss": None}
    wins = net[net > 0]
    losses = net[net <= 0]
    return {
        "n": n, "total": float(net.sum()), "mean": float(net.mean()),
        "win_rate": float((net > 0).mean()),
        "avg_win": float(wins.mean()) if len(wins) else None,
        "avg_loss": float(losses.mean()) if len(losses) else None,
    }


def _exit_dist_str(sub: pd.DataFrame) -> str:
    if sub.empty:
        return ""
    vc = sub["exit_reason"].value_counts()
    return ", ".join(f"{k}={v}" for k, v in vc.items())


def _money(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "—"
    return f"${v:+,.2f}"


def _pct(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "—"
    return f"{v*100:.1f}%"


def main() -> int:
    targets, avail = _availability()
    available_both = [d for d, a in avail.items() if a["es"] and a["gex"]]
    print(f"data availability: {len(available_both)} of {len(targets)} target dates have ES + GEX")
    if len(available_both) < 5:
        print("STOP: fewer than 5 dates have both files.")
        return 1

    print(f"running locked OMEN on {len(available_both)} sessions ...")
    trades = _run_omen(available_both)
    print(f"  raw trades: {len(trades)}")
    if trades.empty:
        print("no trades; aborting before churn join.")
        return 0

    print("joining OneMinL2 churn ...")
    trades, corpus_dates = _join_churn(trades)
    corpus_max_date = max(corpus_dates) if corpus_dates else None
    gap_dates = sorted({d for d in trades["date"] if d not in corpus_dates})
    n_with_churn = int(trades["churn_at_signal"].notna().sum())
    n_nan = int(trades["churn_at_signal"].isna().sum())
    print(f"  trades with churn: {n_with_churn}")
    print(f"  trades NaN (corpus gap): {n_nan} on dates: {gap_dates}")

    trades["bucket"] = trades.apply(_bucket, axis=1)

    sub_high = trades[trades["bucket"] == "HIGH"]
    sub_low = trades[trades["bucket"] == "LOW"]
    sub_nan = trades[trades["bucket"] == "NaN"]
    sub_all = trades

    s_all = _stats(sub_all["net_dollars"])
    s_high = _stats(sub_high["net_dollars"])
    s_low = _stats(sub_low["net_dollars"])
    s_nan = _stats(sub_nan["net_dollars"])

    n_sessions = int(trades["date"].nunique())

    # --- build the report ---
    L: list[str] = []
    L.append("# May 2026 OMEN forward log — churn-filter counterfactual")
    L.append("")
    L.append(f"Generated: {pd.Timestamp.now().strftime('%Y-%m-%dT%H:%M:%S')}")
    L.append("Branch: `main` (read-only on cheese/, locked config)")
    L.append("Source data: locked OMEN pipeline; OneMinL2 corpus_1min.parquet for churn.")
    L.append("")

    L.append("## Note on simulator choice")
    L.append("")
    L.append("> NOTE ON SIMULATOR CHOICE: This report uses the canonical "
             "backtest engine (cheese.backtest.run) which enforces "
             "max_concurrent_positions=1. A prior forward_test report "
             "dated 2026-05-14 (cell_breakdown.md) used a custom 1s "
             "walk-forward simulator that does NOT enforce concurrency "
             "and produced a 6-trade list including a phantom 12:40 "
             "LONG that would have been blocked live by the open 12:30 "
             "SHORT. The canonical 5-trade count in this report "
             "supersedes the prior 6-trade count for live-tradeable "
             "analysis. The cell_breakdown.md file should not be used "
             "for live-tradeable conclusions.")
    L.append("")

    L.append("## Required disclosures")
    L.append("")
    L.append(f"> (a) This is an observational forward-data log. May 2026 to "
             f"date represents approximately {n_sessions} sessions, far below "
             "the 30-session minimum required by "
             "`diagnostics/forward-test-prereg/PREREG.md` for any hypothesis "
             "verdict. No statistical conclusions are drawn from this report.")
    L.append("")
    L.append("> (b) The churn threshold 313.5333 e/s was derived from the "
             "IS-corpus median in the consumed-data stratification "
             "diagnostic. Applying it to forward data is exploratory only. "
             "A threshold tuned on consumed data tested against forward "
             "data is not a clean out-of-sample evaluation — it is a "
             "plausibility check.")
    L.append("")
    L.append(f"> (c) {n_nan} of {len(trades)} trades have NaN churn due to "
             f"OneMinL2 corpus gap beyond date {corpus_max_date}. Those "
             "trades cannot be evaluated under the filter and are excluded "
             "from the counterfactual view but included in the full forward "
             "log.")
    L.append("")

    L.append("## Step 1 — Data availability")
    L.append("")
    L.append("Target window: 2026-05-01 → 2026-05-14")
    L.append("")
    L.append("| date | ES bars | GEX | OneMinL2 churn |")
    L.append("|---|:---:|:---:|:---:|")
    for d in targets:
        es_ok = "✓" if avail[d]["es"] else "✗"
        gex_ok = "✓" if avail[d]["gex"] else "✗"
        churn_ok = "✓" if d in corpus_dates else "✗ (gap)"
        L.append(f"| {d} | {es_ok} | {gex_ok} | {churn_ok} |")
    L.append("")
    L.append(f"Sessions with **ES + GEX**: **{len(available_both)}** "
             f"({', '.join(str(d) for d in available_both)})")
    L.append(f"OneMinL2 corpus last date: **{corpus_max_date}**")
    L.append(f"Corpus-gap dates (no churn available): "
             f"{', '.join(str(d) for d in gap_dates) if gap_dates else '(none)'}")
    L.append("")

    L.append("## Step 2 — Locked OMEN run summary")
    L.append("")
    L.append("Config (locked, do not modify):")
    L.append("```")
    L.append(f"z_threshold:           {Z_THRESHOLD}")
    L.append("stop_atr_mult:         2.0")
    L.append("target_atr_mult:       4.5")
    L.append("atr_window_bars:       14")
    L.append("feature_lookback_bars: 20")
    L.append("trail_after_r:         0")
    L.append(f"time_stop_min:         {TIME_STOP_MIN}")
    L.append(f"blackout_lunch:        {BLACKOUT_LUNCH}  (window [10:30, 12:30) ET)")
    L.append(f"bar_freq:              {BAR_FREQ}")
    L.append("```")
    L.append("")
    L.append(f"Total May trades: **{len(trades)}**")
    L.append(f"Trades with churn value: **{n_with_churn}**")
    L.append(f"Trades with NaN churn (corpus gap): **{n_nan}**")
    if gap_dates:
        L.append(f"Affected dates: {', '.join(str(d) for d in gap_dates)}")
    L.append("")

    L.append("## Step 4 — High-churn filter counterfactual")
    L.append("")
    L.append(f"Locked split: churn_at_signal ≥ **{CHURN_THRESHOLD}** "
             "(IS median, not recomputed)")
    L.append("")
    L.append("| Bucket | n | Total PnL | Mean PnL | Win % | Avg win | Avg loss | Exit dist |")
    L.append("|---|---:|---:|---:|---:|---:|---:|---|")

    def _row(label, st, sub):
        return (f"| {label} | {st['n']} | {_money(st['total'])} "
                f"| {_money(st['mean'])} | {_pct(st['win_rate'])} "
                f"| {_money(st['avg_win'])} | {_money(st['avg_loss'])} "
                f"| {_exit_dist_str(sub)} |")

    L.append(_row("Full May (all trades incl NaN)", s_all, sub_all))
    L.append(_row("HIGH (churn ≥ 313.5333)", s_high, sub_high))
    L.append(_row("LOW (churn < 313.5333)", s_low, sub_low))
    L.append(_row("NaN (excluded from filter view)", s_nan, sub_nan))
    L.append("")
    L.append("**High-churn filter applied (counterfactual):** the HIGH bucket "
             "restated as the full filter view. Trades with NaN churn are "
             "excluded because the filter cannot be evaluated on them.")
    L.append("")
    L.append(f"- n: **{s_high['n']}**, total PnL: **{_money(s_high['total'])}**, "
             f"win rate: **{_pct(s_high['win_rate'])}**")
    L.append("")
    L.append("**Low-churn filter applied (symmetry view):**")
    L.append("")
    L.append(f"- n: **{s_low['n']}**, total PnL: **{_money(s_low['total'])}**, "
             f"win rate: **{_pct(s_low['win_rate'])}**")
    L.append("")
    L.append(f"**Context — NaN bucket carries the worst PnL of the month "
             f"so far.** The {n_nan} corpus-gap trades on "
             f"{', '.join(str(d) for d in gap_dates)} total "
             f"**{_money(s_nan['total'])}** "
             f"(win rate {_pct(s_nan['win_rate'])}) — a larger drawdown "
             f"than the entire HIGH+LOW evaluated set combined "
             f"({_money(s_high['total'] + s_low['total'])}). Because "
             "those sessions fall beyond the OneMinL2 corpus "
             f"({corpus_max_date}), they cannot be churn-bucketed and "
             "are excluded from the filter counterfactual while remaining "
             "in the full forward log. Any future reader should note that "
             "the filter view therefore omits the month's worst sessions.")
    L.append("")

    L.append("## Step 5 — Per-trade log (full)")
    L.append("")
    L.append("| date | entry_ts (ET) | dir | cell | churn_at_signal | bucket | exit | net $ | notes |")
    L.append("|---|---|---|---|---:|---|---|---:|---|")
    for _, row in trades.sort_values("entry_time").iterrows():
        ets = row["entry_time_et"].strftime("%H:%M:%S")
        ch = row["churn_at_signal"]
        ch_str = "NaN" if pd.isna(ch) else f"{ch:.2f}"
        notes = []
        if row.get("opening_bar_fallback"):
            notes.append("opening-bar fallback")
        if row.get("corpus_gap"):
            notes.append("corpus gap")
        L.append(
            f"| {row['date']} | {ets} | {row['direction']} | {row['cell_label']} "
            f"| {ch_str} | {row['bucket']} | {row['exit_reason']} "
            f"| {_money(float(row['net_dollars']))} | {'; '.join(notes)} |"
        )
    L.append("")

    L.append("## Step 6 — Cell breakdown (context only)")
    L.append("")
    L.append("| cell | n | total PnL | mean PnL | win rate |")
    L.append("|---|---:|---:|---:|---:|")
    for cell in ("LONG_long", "LONG_short", "SHORT_long", "SHORT_short"):
        sub = trades[trades["cell_label"] == cell]
        st = _stats(sub["net_dollars"])
        L.append(
            f"| {cell} | {st['n']} | {_money(st['total'])} "
            f"| {_money(st['mean'])} | {_pct(st['win_rate'])} |"
        )
    L.append("")

    OUT_PATH.write_text("\n".join(L))
    print(f"wrote {OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
