"""
Time-accurate trade + MBP-10 stream: live Databento or CSV replay merged on ts_event.
Liquidity walls: bid/ask levels with resting size > WALL_SIZE_THRESHOLD emit wall_delta events.
"""
from __future__ import annotations

import csv
import os
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Dict, List, Optional, Tuple

import dotenv
from datetime import datetime, timezone

dotenv.load_dotenv()

DATABENTO_API_KEY = os.getenv("DATABENTO_API_KEY")
dataset = "GLBX.MDP3"
symbol = "NQM6"

# Resting liquidity threshold (contracts / size units at level)
WALL_SIZE_THRESHOLD = 60

# Default CSV paths relative to cwd (run from backend/)
DEFAULT_TRADES_CSV = "trades.csv"
DEFAULT_BOOK_CSV = "book.csv"

TickCallback = Callable[[Dict[str, Any]], None]
WallDeltaCallback = Callable[[Dict[str, Any]], None]


def _ts_event_ns_from_row(row: Dict[str, str]) -> int:
    """Parse ts_event from CSV to integer nanoseconds since Unix epoch (UTC)."""
    s = row["ts_event"].strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    # pandas-style: "2026-03-19 14:30:00.002917187+00:00"
    if " " in s and "T" not in s:
        s = s.replace(" ", "T", 1)
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1_000_000_000)


def _price_key(p: float) -> float:
    """Stable dict key for ladder prices."""
    return round(float(p), 9)


class WallDetector:
    """
    O(10) per update: track bid/ask levels with size > threshold; emit deltas only when changed.
    """

    __slots__ = ("_bid", "_ask", "threshold")

    def __init__(self, threshold: int = WALL_SIZE_THRESHOLD) -> None:
        self.threshold = threshold
        self._bid: Dict[float, int] = {}
        self._ask: Dict[float, int] = {}

    def process_levels(
        self,
        bid_px: List[float],
        bid_sz: List[int],
        ask_px: List[float],
        ask_sz: List[int],
        ts_sec: Optional[float] = None,
    ) -> Optional[Dict[str, Any]]:
        new_bid: Dict[float, int] = {}
        new_ask: Dict[float, int] = {}
        for i in range(10):
            bp, bs = bid_px[i], bid_sz[i]
            ap, az = ask_px[i], ask_sz[i]
            if bs > self.threshold:
                new_bid[_price_key(bp)] = int(bs)
            if az > self.threshold:
                new_ask[_price_key(ap)] = int(az)

        added: List[Dict[str, Any]] = []
        removed: List[Dict[str, Any]] = []

        for p, sz in new_bid.items():
            if p not in self._bid or self._bid[p] != sz:
                added.append({"side": "bid", "price": float(p), "size": int(sz)})
        for p in self._bid:
            if p not in new_bid:
                removed.append({"side": "bid", "price": float(p)})

        for p, sz in new_ask.items():
            if p not in self._ask or self._ask[p] != sz:
                added.append({"side": "ask", "price": float(p), "size": int(sz)})
        for p in self._ask:
            if p not in new_ask:
                removed.append({"side": "ask", "price": float(p)})

        self._bid = new_bid
        self._ask = new_ask

        if not added and not removed:
            return None
        out: Dict[str, Any] = {"added": added, "removed": removed}
        if ts_sec is not None:
            out["ts"] = ts_sec
        return out

    def process_csv_row(self, row: Dict[str, str]) -> Optional[Dict[str, Any]]:
        bid_px = [float(row[f"bid_px_{i:02d}"]) for i in range(10)]
        bid_sz = [int(row[f"bid_sz_{i:02d}"]) for i in range(10)]
        ask_px = [float(row[f"ask_px_{i:02d}"]) for i in range(10)]
        ask_sz = [int(row[f"ask_sz_{i:02d}"]) for i in range(10)]
        ts_sec = _ts_event_ns_from_row(row) / 1e9
        return self.process_levels(bid_px, bid_sz, ask_px, ask_sz, ts_sec=ts_sec)

    def reset(self) -> None:
        self._bid.clear()
        self._ask.clear()


def _levels_from_mbp_record(rec: Any) -> Optional[Tuple[List[float], List[int], List[float], List[int]]]:
    """Extract top-10 ladder from a live Databento MBP-10 record (duck-typed)."""
    levels = getattr(rec, "levels", None)
    if not levels:
        return None
    n = min(10, len(levels))
    bid_px: List[float] = []
    bid_sz: List[int] = []
    ask_px: List[float] = []
    ask_sz: List[int] = []
    for i in range(n):
        lv = levels[i]
        # DBN-style fixed-point prices (int ns) or floats from CSV-like wrappers
        bpx = getattr(lv, "bid_px", None)
        apx = getattr(lv, "ask_px", None)
        if bpx is not None:
            if isinstance(bpx, (int, float)) and not isinstance(bpx, bool):
                # likely fixed-point int
                bp_f = float(bpx) / 1e9 if abs(bpx) > 1e6 else float(bpx)
            else:
                bp_f = float(bpx)
        else:
            bp_f = 0.0
        if apx is not None:
            if isinstance(apx, (int, float)) and not isinstance(apx, bool):
                ap_f = float(apx) / 1e9 if abs(apx) > 1e6 else float(apx)
            else:
                ap_f = float(apx)
        else:
            ap_f = 0.0
        bid_px.append(bp_f)
        ask_px.append(ap_f)
        bid_sz.append(int(getattr(lv, "bid_sz", 0) or 0))
        ask_sz.append(int(getattr(lv, "ask_sz", 0) or 0))
    while len(bid_px) < 10:
        bid_px.append(0.0)
        ask_px.append(0.0)
        bid_sz.append(0)
        ask_sz.append(0)
    return bid_px, bid_sz, ask_px, ask_sz


class DatastreamEngine:
    def __init__(self) -> None:
        print("Initializing Datastream Engine")
        self._live_client: Any = None
        self._tick_callbacks: List[TickCallback] = []
        self._mbp_callbacks: List[WallDeltaCallback] = []
        self._wall_detector = WallDetector(WALL_SIZE_THRESHOLD)
        self._sim_thread: Optional[threading.Thread] = None
        # Lightweight counters (optional diagnostics for throughput tuning)
        self.stats: Dict[str, int] = {"ticks_emitted": 0, "wall_deltas_emitted": 0}

    def _get_live_client(self) -> Any:
        if self._live_client is None:
            import databento as db

            self._live_client = db.Live(DATABENTO_API_KEY)
        return self._live_client

    def subscribe(self, callback: TickCallback) -> None:
        """Backward-compatible alias for tick subscription."""
        self._tick_callbacks.append(callback)

    def subscribe_tick(self, callback: TickCallback) -> None:
        self._tick_callbacks.append(callback)

    def subscribe_mbp(self, callback: WallDeltaCallback) -> None:
        self._mbp_callbacks.append(callback)

    def _emit_tick(self, clean: Dict[str, Any]) -> None:
        self.stats["ticks_emitted"] += 1
        for cb in self._tick_callbacks:
            cb(clean)

    def _emit_wall_delta(self, delta: Dict[str, Any]) -> None:
        self.stats["wall_deltas_emitted"] += 1
        for cb in self._mbp_callbacks:
            cb(delta)

    def start(self) -> None:
        client = self._get_live_client()
        client.subscribe(
            dataset=dataset,
            schema="trades",
            symbols=symbol,
            stype_in="raw_symbol",
        )
        client.subscribe(
            dataset=dataset,
            schema="mbp-10",
            symbols=symbol,
            stype_in="raw_symbol",
        )
        client.add_callback(self._on_live_record)
        client.start()

    def start_simulated(
        self,
        trades_path: str = DEFAULT_TRADES_CSV,
        book_path: str = DEFAULT_BOOK_CSV,
    ) -> None:
        trades_p = Path(trades_path)
        book_p = Path(book_path)
        if not trades_p.is_file():
            raise FileNotFoundError(f"Trades CSV not found: {trades_p.resolve()}")
        if not book_p.is_file():
            raise FileNotFoundError(f"Book CSV not found: {book_p.resolve()}")

        def sim() -> None:
            self._wall_detector.reset()
            with trades_p.open(newline="") as tf, book_p.open(newline="") as bf:
                tr = csv.DictReader(tf)
                br = csv.DictReader(bf)
                row_t = next(tr, None)
                row_b = next(br, None)
                prev_ns: Optional[int] = None

                class Tick:
                    __slots__ = ("pretty_price", "side", "size", "ts_event")

                    def __init__(self, price: Any, side: str, size: Any, ts_event: int) -> None:
                        self.pretty_price = price
                        self.side = side
                        self.size = size
                        self.ts_event = ts_event

                while row_t is not None or row_b is not None:
                    if row_b is None:
                        kind, row = "t", row_t
                        row_t = next(tr, None)
                    elif row_t is None:
                        kind, row = "b", row_b
                        row_b = next(br, None)
                    else:
                        nt = _ts_event_ns_from_row(row_t)
                        nb = _ts_event_ns_from_row(row_b)
                        if nt < nb:
                            kind, row = "t", row_t
                            row_t = next(tr, None)
                        elif nb < nt:
                            kind, row = "b", row_b
                            row_b = next(br, None)
                        else:
                            # Same ts_event: apply book first so wall state matches this trade print
                            kind, row = "b", row_b
                            row_b = next(br, None)

                    cur_ns = _ts_event_ns_from_row(row)
                    if prev_ns is not None:
                        delay = (cur_ns - prev_ns) / 1e9
                        if delay > 0:
                            time.sleep(delay)
                    prev_ns = cur_ns

                    if kind == "t":
                        self._on_tick(
                            Tick(
                                row["price"],
                                row["side"],
                                row["size"],
                                cur_ns,
                            )
                        )
                    else:
                        delta = self._wall_detector.process_csv_row(row)
                        if delta is not None:
                            self._emit_wall_delta(delta)

        thread = threading.Thread(target=sim, daemon=True)
        self._sim_thread = thread
        thread.start()

    def _on_tick(self, tick: Any) -> None:
        try:
            price = float(tick.pretty_price)
            sch = str(tick.side).upper()[:1]
            side = int(-1 if sch == "A" else 1)
            size = int(float(tick.size))
            ts = float(tick.ts_event / 1_000_000_000)

            clean_tick = {
                "price": price,
                "side": side,
                "size": size,
                "ts": ts,
            }
            self._emit_tick(clean_tick)
        except Exception as e:
            print(e)

    def _on_live_record(self, rec: Any) -> None:
        """Route live Databento records to tick or MBP wall processing."""
        rtype = getattr(rec, "rtype", None)
        rv = getattr(rtype, "value", rtype)
        try:
            rti = int(rv) if rv is not None else None
        except (TypeError, ValueError):
            rti = None
        levels = getattr(rec, "levels", None)

        # MBP-10 first (DBN rtype 10; depth ladder in .levels)
        if rti == 10 or (levels is not None and len(levels) >= 10):
            lv = _levels_from_mbp_record(rec)
            if lv is None:
                return
            bid_px, bid_sz, ask_px, ask_sz = lv
            ts_event = int(getattr(rec, "ts_event", 0))
            ts_sec = ts_event / 1e9 if ts_event else None
            delta = self._wall_detector.process_levels(
                bid_px, bid_sz, ask_px, ask_sz, ts_sec=ts_sec
            )
            if delta is not None:
                self._emit_wall_delta(delta)
            return

        # Trades
        if hasattr(rec, "pretty_price") and hasattr(rec, "side"):
            try:
                ts_event = int(getattr(rec, "ts_event", 0))
                if ts_event == 0:
                    return

                def _side_char(s: Any) -> str:
                    if isinstance(s, str) and s:
                        return s[0]
                    if isinstance(s, (bytes, bytearray)):
                        return s.decode("ascii", errors="ignore")[:1] or "N"
                    if isinstance(s, int):
                        return chr(s) if 0 <= s < 128 else "N"
                    sn = getattr(s, "name", None)
                    if isinstance(sn, str) and sn:
                        return "A" if "ASK" in sn.upper() else ("B" if "BID" in sn.upper() else sn[0])
                    return str(s)[0] if s is not None else "N"

                self._on_tick(
                    SimpleNamespace(
                        pretty_price=rec.pretty_price,
                        side=_side_char(rec.side),
                        size=rec.size,
                        ts_event=ts_event,
                    )
                )
            except Exception as e:
                print("live tick error:", e)
            return
