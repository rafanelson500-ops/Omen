"""
Paper trading: enter when last trade price is exactly 1 tick from an opposite-side wall;
fill on the next trade tick; max one position; TP = 4 ticks, SL = 8 ticks.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, Optional

EmitFn = Callable[[str, Dict[str, Any]], None]


def _price_key(p: float) -> float:
    return round(float(p), 9)


class PaperTrader:
    TICK_SIZE = 0.25
    TP_TICKS = 4
    SL_TICKS = 4

    __slots__ = (
        "_emit",
        "bid_walls",
        "ask_walls",
        "position",
        "pending",
        "_next_id",
    )

    def __init__(self, emit: EmitFn) -> None:
        self._emit = emit
        self.bid_walls: Dict[float, int] = {}
        self.ask_walls: Dict[float, int] = {}
        self.position: Optional[Dict[str, Any]] = None
        self.pending: Optional[Dict[str, Any]] = None
        self._next_id = 1

    def reset(self) -> None:
        self.bid_walls.clear()
        self.ask_walls.clear()
        self.position = None
        self.pending = None

    def on_wall_delta(self, delta: Dict[str, Any]) -> None:
        for r in delta.get("removed", []) or []:
            pk = _price_key(r["price"])
            if r["side"] == "bid":
                self.bid_walls.pop(pk, None)
            else:
                self.ask_walls.pop(pk, None)
        for a in delta.get("added", []) or []:
            pk = _price_key(a["price"])
            if a["side"] == "bid":
                self.bid_walls[pk] = int(a["size"])
            else:
                self.ask_walls[pk] = int(a["size"])

    def _tick_index(self, price: float) -> int:
        return int(round(price / self.TICK_SIZE))

    def _check_signal(self, price: float) -> Optional[Dict[str, Any]]:
        """Long: price 1 tick above a bid wall. Short: price 1 tick below an ask wall."""
        pi = self._tick_index(price)
        for w in self.bid_walls:
            wi = self._tick_index(float(w))
            if pi == wi + 1:
                return {"side": "long", "wall_price": float(w)}
        for w in self.ask_walls:
            wi = self._tick_index(float(w))
            if pi == wi - 1:
                return {"side": "short", "wall_price": float(w)}
        return None

    def _open(self, side: str, entry: float, ts: float, wall_price: float) -> None:
        tid = str(self._next_id)
        self._next_id += 1
        tsz = self.TICK_SIZE
        if side == "long":
            tp = entry + self.TP_TICKS * tsz
            sl = entry - self.SL_TICKS * tsz
        else:
            tp = entry - self.TP_TICKS * tsz
            sl = entry + self.SL_TICKS * tsz

        self.position = {
            "id": tid,
            "side": side,
            "entry": entry,
            "take_profit": tp,
            "stop_loss": sl,
            "ts": ts,
            "wall_price": wall_price,
        }
        self._emit(
            "trade_opened",
            {
                "id": tid,
                "side": side,
                "entry": entry,
                "take_profit": tp,
                "stop_loss": sl,
                "ts": ts,
                "wall_price": wall_price,
            },
        )

    def _close(self, reason: str, exit_price: float, ts: float) -> None:
        if not self.position:
            return
        pos = self.position
        self.position = None
        entry = float(pos["entry"])
        side = pos["side"]
        tid = pos["id"]

        if side == "long":
            pnl_ticks = (exit_price - entry) / self.TICK_SIZE
        else:
            pnl_ticks = (entry - exit_price) / self.TICK_SIZE

        self._emit(
            "trade_closed",
            {
                "id": tid,
                "side": side,
                "entry": entry,
                "exit": exit_price,
                "reason": reason,
                "pnl_ticks": round(pnl_ticks, 4),
                "ts": ts,
            },
        )

    def on_tick(self, tick: Dict[str, Any]) -> None:
        price = float(tick["price"])
        ts = float(tick["ts"])

        # 1) Manage open position (SL/TP on this print)
        if self.position is not None:
            side = self.position["side"]
            tp = float(self.position["take_profit"])
            sl = float(self.position["stop_loss"])
            hit_sl = False
            hit_tp = False
            if side == "long":
                if price <= sl:
                    hit_sl = True
                if price >= tp:
                    hit_tp = True
            else:
                if price >= sl:
                    hit_sl = True
                if price <= tp:
                    hit_tp = True
            if hit_sl and hit_tp:
                hit_sl = True
            if hit_sl:
                self._close("sl", price, ts)
                return
            if hit_tp:
                self._close("tp", price, ts)
                return
            # Still in a trade — do not arm new signals or fill other state
            return

        # 2) Fill pending entry on this (next) trade tick
        if self.pending is not None:
            pend = self.pending
            self.pending = None
            self._open(
                pend["side"],
                price,
                ts,
                float(pend["wall_price"]),
            )
            return

        # 3) New signal (flat, no pending)
        sig = self._check_signal(price)
        if sig is not None:
            self.pending = {
                "side": sig["side"],
                "wall_price": sig["wall_price"],
                "signal_ts": ts,
                "signal_price": price,
            }
            self._emit(
                "trade_pending",
                {
                    "side": sig["side"],
                    "signal_price": price,
                    "wall_price": sig["wall_price"],
                    "ts": ts,
                },
            )
