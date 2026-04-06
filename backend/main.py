import threading

import numpy as np
from flask import Flask
from flask_socketio import SocketIO, emit
import pandas as pd
from classes.datastream import Datastream, aggregate_ticks
from classes.strategy import Strategy
from classes.features import (
    LIVE_LONG_WARMUP,
    LIVE_MEDIUM_WARMUP,
    LIVE_TICK_WARMUP,
    add_context_features,
    add_tick_features,
    microstate_features,
)

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")


def _live_master_row_slice(
    short_df: pd.DataFrame,
    medium_df: pd.DataFrame,
    long_df: pd.DataFrame,
) -> pd.DataFrame | None:
    """One master row to append, or None — same rules as live ``on_tick``."""
    if len(short_df) < LIVE_TICK_WARMUP:
        return None
    if not (
        len(medium_df) >= LIVE_MEDIUM_WARMUP
        and "raw_delta" in medium_df.columns
        and "avg_delta" in medium_df.columns
        and len(long_df) >= LIVE_LONG_WARMUP
        and "vwap" in long_df.columns
        and "vwap_std" in long_df.columns
        and "hmm_state" in long_df.columns
    ):
        return None
    row_df = short_df.iloc[-1:].copy()
    last_m = medium_df.iloc[-1]
    last_l = long_df.iloc[-1]
    row_df["raw_delta"] = last_m["raw_delta"]
    row_df["avg_delta"] = last_m["avg_delta"]
    vw = float(last_l["vwap"])
    vst = float(last_l["vwap_std"])
    row_df["vwap"] = vw
    row_df["vwap_std"] = vst
    # Same as Strategy.backtest(): ingest_tick expects these keys on the live row.
    row_df["vwap_upper"] = vw + 2.0 * vst
    row_df["vwap_lower"] = vw - 2.0 * vst
    row_df["hmm_state"] = last_l["hmm_state"]
    return row_df


def build_master_df_live_replay(raw_short: pd.DataFrame) -> pd.DataFrame:
    """
    Build the same ``master_df`` live would produce, without a per-tick Python loop.

    Live uses non-overlapping 10- and 100-tick buffers; after ``i`` ticks (1-based count
    ``c``), completed medium bars = ``c // 10`` and long bars = ``c // 100``. Rolling
    features on ticks and on bar series are **causal**, so one vectorized pass over the
    full tick table plus NumPy indexing matches incremental concat + ``rolling``.
    """
    cols = ["time", "open", "high", "low", "close", "volume", "delta"]
    if raw_short.empty or not all(c in raw_short.columns for c in cols):
        return pd.DataFrame()

    work = raw_short[cols].reset_index(drop=True)
    n = len(work)
    if n == 0:
        return pd.DataFrame()

    short_feat = add_tick_features(work.copy())
    med_bars = aggregate_ticks(work, 10)
    long_bars = aggregate_ticks(work, 100)

    medium_feat = microstate_features(med_bars) if not med_bars.empty else pd.DataFrame()
    long_feat = add_context_features(long_bars) if not long_bars.empty else pd.DataFrame()

    ticks_done = np.arange(1, n + 1, dtype=np.int64)
    n_med = ticks_done // 10
    n_long = ticks_done // 100

    need = (
        (ticks_done >= LIVE_TICK_WARMUP)
        & (n_med >= LIVE_MEDIUM_WARMUP)
        & (n_long >= LIVE_LONG_WARMUP)
    )
    if not need.any():
        return pd.DataFrame()

    if medium_feat.empty or long_feat.empty:
        return pd.DataFrame()
    if not (
        {"raw_delta", "avg_delta"}.issubset(medium_feat.columns)
        and {"vwap", "vwap_std", "hmm_state"}.issubset(long_feat.columns)
    ):
        return pd.DataFrame()

    med_ix = n_med - 1
    long_ix = n_long - 1

    out = short_feat.loc[need].copy()
    mraw = medium_feat["raw_delta"].to_numpy()
    mavg = medium_feat["avg_delta"].to_numpy()
    lvw = long_feat["vwap"].to_numpy()
    lvs = long_feat["vwap_std"].to_numpy()
    lhmm = long_feat["hmm_state"].to_numpy()
    out["raw_delta"] = mraw[med_ix[need]]
    out["avg_delta"] = mavg[med_ix[need]]
    out["vwap"] = lvw[long_ix[need]]
    out["vwap_std"] = lvs[long_ix[need]]
    out["vwap_upper"] = out["vwap"] + 2.0 * out["vwap_std"]
    out["vwap_lower"] = out["vwap"] - 2.0 * out["vwap_std"]
    out["hmm_state"] = lhmm[long_ix[need]]
    return out.reset_index(drop=True)


def _filter_rth_utc(df: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    """Keep rows whose ``time`` column (Unix seconds) falls in [start, end] UTC time-of-day."""
    if df.empty or "time" not in df.columns:
        return df
    idx = pd.DatetimeIndex(pd.to_datetime(df["time"], unit="s", utc=True))
    loc = idx.indexer_between_time(start, end, include_start=True, include_end=True)
    return df.iloc[loc].copy()


def _emit_from_live(event: str, payload: dict) -> None:
    """Broadcast from Databento thread (Flask-SocketIO threading mode)."""
    with app.app_context():
        socketio.emit(event, payload, namespace="/")


@socketio.on("connect")
def handle_connect():
    print("Client connected")
    emit("connected")


@socketio.on("disconnect")
def handle_disconnect():
    print("Client disconnected")
    emit("disconnected")


@socketio.on("backtest")
def handle_backtest(date):
    print(f"Backtesting on {date}")
    backtest(date + "T13:20:00.000000000Z", date + "T14:00:00.000000000Z")


def backtest(start_date, end_date):
    datastream = Datastream()
    strategy = Strategy()
    short_raw, medium_df, long_df = datastream.historical(start_date, end_date)
    # Same sequence as live: replay from fetch start so rolling/buffers match stream order.
    master_df = build_master_df_live_replay(short_raw)

    short_df = add_tick_features(short_raw.copy())
    medium_df = microstate_features(medium_df)
    long_df = add_context_features(long_df)

    short_df = _filter_rth_utc(short_df, "13:30:00", "15:30:00")
    medium_df = _filter_rth_utc(medium_df, "13:30:00", "15:30:00")
    long_df = _filter_rth_utc(long_df, "13:30:00", "15:30:00")
    master_df = _filter_rth_utc(master_df, "13:30:00", "15:30:00")

    short_df.dropna(inplace=True)
    medium_df.dropna(inplace=True)
    long_df.dropna(inplace=True)
    master_df.dropna(inplace=True)

    master_df = strategy.backtest(master_df)
    # Index labels differ (short keeps historical index; master is reset 0..n). Align on time.
    short_df = short_df.merge(
        master_df[["time", "position", "unrealizedpnl", "realizedpnl"]],
        on="time",
        how="left",
    )

    short_df["totalpnl"] = short_df["unrealizedpnl"] + short_df["realizedpnl"]

    socketio.emit(
        "backtest",
        {
            "tick": short_df.to_dict(orient="records"),
            "10-tick": medium_df.to_dict(orient="records"),
            "100-tick": long_df.to_dict(orient="records"),
        },
    )


def start_live_stream() -> None:
    """Run Databento live client in a daemon thread so the HTTP server can bind."""

    master_df = pd.DataFrame()
    short_df = pd.DataFrame()
    medium_df = pd.DataFrame()
    long_df = pd.DataFrame()
    strategy = Strategy()
    
    def on_tick(row: dict) -> None:
        nonlocal short_df, master_df
        short_df = pd.concat([short_df, pd.DataFrame([row])], ignore_index=True)
        short_df = add_tick_features(short_df)
        piece = _live_master_row_slice(short_df, medium_df, long_df)
        if piece is not None:
            master_df = pd.concat([master_df, piece], ignore_index=True)
            strategy.live_tick(master_df.iloc[-1])

        if len(short_df) < LIVE_TICK_WARMUP:
            print(f"Warming up {len(short_df)}/{LIVE_TICK_WARMUP}")
            return

        # Full tick row; strategy fields from last ``live_tick`` (runs only when ``piece``
        # is not None). Attach on every emit once master exists so the stream isn’t missing
        # totalpnl on trades that don’t start a new master row (those ticks reuse last state).
        payload = short_df.iloc[-1].to_dict()
        if len(master_df) > 0:
            payload["position"] = strategy.position
            payload["unrealizedpnl"] = strategy.unrealizedpnl
            payload["realizedpnl"] = strategy.realizedpnl
            payload["totalpnl"] = float(strategy.unrealizedpnl) + float(strategy.realizedpnl)
        _emit_from_live("tick", payload)

    def on_medium(row: dict) -> None:
        nonlocal medium_df
        medium_df = pd.concat([medium_df, pd.DataFrame([row])], ignore_index=True)
        medium_df = microstate_features(medium_df)
        if len(medium_df) < LIVE_MEDIUM_WARMUP:
            return
        _emit_from_live("10-tick", medium_df.iloc[-1].to_dict())

    def on_long(row: dict) -> None:
        nonlocal long_df
        long_df = pd.concat([long_df, pd.DataFrame([row])], ignore_index=True)
        long_df = add_context_features(long_df)
        if len(long_df) < LIVE_LONG_WARMUP:
            return
        _emit_from_live("100-tick", long_df.iloc[-1].to_dict())

    stream = Datastream(on_tick, on_medium, on_long)

    def run() -> None:
        try:
            stream.live()
        except Exception as exc:
            print(f"Live stream ended: {exc!r}")

    threading.Thread(target=run, name="databento-live", daemon=True).start()


if __name__ == "__main__":
    start_live_stream()
    socketio.run(app, host="0.0.0.0", port=8000)
