from __future__ import annotations

from dataclasses import dataclass
import uuid

from state_machine import TradeStateMachine


@dataclass
class OpenTrade:
    id: str
    side: str
    entry: float
    take_profit: float
    stop_loss: float
    open_tick_count: int
    setup_type: str


class StrategyEngine:
    """
    100-tick: setup arms a passive limit (pullback) for entry.
    10-tick: regime updates — does not cancel a pending limit unless it expires.
    1-tick: limit fill simulation + position management.
    """

    def __init__(self) -> None:
        self.state = TradeStateMachine()
        self.current_setup: dict[str, object] | None = None
        self.current_regime: dict[str, object] = {
            "tradable": False,
            "type": "chop",
            "volatility": "low",
            "reasons": ["warming_up"],
        }
        self.current_micro: dict[str, float] = {
            "pressure": 0.0,
            "absorption": 0.0,
            "volatility": 0.0,
        }
        self.open_trade: OpenTrade | None = None
        self.pending_entry_price: float | None = None
        self.pending_armed_tick: int | None = None

        self.tick_size = 0.25
        self.min_quality = 0.42
        self.daily_trade_cap = 15
        self.trade_count = 0
        self.tick_counter = 0
        self.max_stall_ticks = 260
        self.min_tp_ticks = 10
        self.pressure_flip_threshold = 0.38
        self.min_ticks_before_flip_exit = 32
        self.trade_cooldown_ticks = 40
        self.last_exit_tick = -1_000_000

        # Pullback limit: more likely to trade than a limit at the 100-tick close alone.
        self.entry_offset_ticks = 2
        self.max_pending_ticks = 600

    def on_regime(self, regime: dict[str, object], ts: float) -> list[tuple[str, dict[str, object]]]:
        self.current_regime = regime
        events: list[tuple[str, dict[str, object]]] = [("strategy_regime", regime)]

        if bool(regime.get("tradable")):
            return events

        # Do not cancel an armed limit or an open position on a soft regime flip.
        if self.state.state in (TradeStateMachine.WAITING_TRIGGER, TradeStateMachine.IN_TRADE):
            events.append(
                (
                    "strategy_decision",
                    {
                        "kind": "regime_suboptimal_ignored",
                        "ts": ts,
                        "reasons": regime.get("reasons", []),
                    },
                )
            )
            return events

        self.current_setup = None
        self.pending_entry_price = None
        self.pending_armed_tick = None
        self.state.transition(TradeStateMachine.IDLE)
        events.append(
            (
                "strategy_decision",
                {"kind": "blocked_by_regime", "ts": ts, "reasons": regime.get("reasons", [])},
            )
        )
        events.append(self._state_event(side=None, entry_gate_open=False))
        return events

    def on_setup(self, setup: dict[str, object], ts: float, signal_price: float) -> list[tuple[str, dict[str, object]]]:
        if not bool(self.current_regime.get("tradable")):
            self.state.transition(TradeStateMachine.IDLE)
            return [
                (
                    "strategy_decision",
                    {"kind": "blocked_by_regime", "ts": ts, "reasons": self.current_regime.get("reasons", [])},
                ),
                self._state_event(side=None, entry_gate_open=False),
            ]

        quality = float(setup.get("quality") or 0.0)
        direction_raw = setup.get("direction")
        setup_type = setup.get("type")
        if setup_type is None or direction_raw is None or quality < self.min_quality:
            self.state.transition(TradeStateMachine.IDLE)
            return [
                ("strategy_setup", setup),
                (
                    "strategy_decision",
                    {"kind": "no_setup", "ts": ts, "reasons": setup.get("reasons", [])},
                ),
                self._state_event(side=None, entry_gate_open=False),
            ]

        if self.trade_count >= self.daily_trade_cap:
            self.state.transition(TradeStateMachine.IDLE)
            return [
                ("strategy_setup", setup),
                (
                    "strategy_decision",
                    {"kind": "daily_cap_reached", "ts": ts, "reasons": ["daily_trade_cap"]},
                ),
                self._state_event(side=None, entry_gate_open=False),
            ]

        if (self.tick_counter - self.last_exit_tick) < self.trade_cooldown_ticks:
            ticks_remaining = self.trade_cooldown_ticks - (self.tick_counter - self.last_exit_tick)
            self.state.transition(TradeStateMachine.IDLE)
            return [
                ("strategy_setup", setup),
                (
                    "strategy_decision",
                    {"kind": "cooldown_active", "ts": ts, "reasons": [f"wait_{ticks_remaining}_ticks"]},
                ),
                self._state_event(side=None, entry_gate_open=False),
            ]

        # Invert vs detector: trade the opposite side.
        direction = "short" if direction_raw == "long" else "long"
        setup = {**setup, "direction": direction}
        self.current_setup = setup
        events: list[tuple[str, dict[str, object]]] = [("strategy_setup", setup)]

        self.state.transition(TradeStateMachine.SETUP_FOUND)
        offset = self.entry_offset_ticks * self.tick_size
        if direction == "long":
            self.pending_entry_price = float(signal_price) - offset
        else:
            self.pending_entry_price = float(signal_price) + offset

        self.pending_armed_tick = self.tick_counter

        events.append(
            (
                "strategy_decision",
                {
                    "kind": "setup_found",
                    "ts": ts,
                    "setup_type": setup_type,
                    "direction": direction,
                    "quality": quality,
                    "signal_price": signal_price,
                    "limit_price": self.pending_entry_price,
                    "reasons": setup.get("reasons", []),
                },
            )
        )
        self.state.transition(TradeStateMachine.WAITING_TRIGGER)
        events.append(self._state_event(side=str(direction), entry_gate_open=True))
        events.append(
            (
                "trade_pending",
                {
                    "ts": ts,
                    "side": direction,
                    "signal_price": signal_price,
                    "wall_price": self.pending_entry_price,
                    "needs_absorption": setup_type == "absorption",
                    "max_trade_ticks": self.max_stall_ticks,
                },
            )
        )
        return events

    def on_tick(
        self, tick_candle: dict[str, float], microstate: dict[str, float]
    ) -> list[tuple[str, dict[str, object]]]:
        self.current_micro = microstate
        ts = float(tick_candle["time"])
        price = float(tick_candle["close"])
        self.tick_counter += 1
        events: list[tuple[str, dict[str, object]]] = [("strategy_microstate", microstate)]

        if self.open_trade is None and self.state.state == TradeStateMachine.WAITING_TRIGGER:
            direction = str((self.current_setup or {}).get("direction") or "")
            entry_price = self.pending_entry_price
            armed_at = self.pending_armed_tick

            if entry_price is None or direction not in {"long", "short"}:
                return events

            if armed_at is not None and (self.tick_counter - armed_at) > self.max_pending_ticks:
                self.pending_entry_price = None
                self.pending_armed_tick = None
                self.current_setup = None
                self.state.transition(TradeStateMachine.IDLE)
                events.append(
                    (
                        "strategy_decision",
                        {"kind": "pending_expired", "ts": ts, "reasons": ["limit_not_filled"]},
                    )
                )
                events.append(self._state_event(side=None, entry_gate_open=False))
                return events

            low = float(tick_candle.get("low", price))
            high = float(tick_candle.get("high", price))
            limit_touched = (direction == "long" and low <= entry_price) or (
                direction == "short" and high >= entry_price
            )

            if limit_touched:
                vol = max(0.2, float(microstate.get("volatility", 0.0)))
                # Swapped vs prior: wide target was SL ticks, tight risk was TP ticks.
                tp_ticks = max(12, round(vol * 22))
                sl_ticks = max(self.min_tp_ticks, round(vol * 8))
                tp = entry_price + (tp_ticks * self.tick_size if direction == "long" else -tp_ticks * self.tick_size)
                sl = entry_price - (sl_ticks * self.tick_size if direction == "long" else -sl_ticks * self.tick_size)

                trade = OpenTrade(
                    id=str(uuid.uuid4())[:8],
                    side=direction,
                    entry=entry_price,
                    take_profit=tp,
                    stop_loss=sl,
                    open_tick_count=self.tick_counter,
                    setup_type=str((self.current_setup or {}).get("type") or "unknown"),
                )
                self.open_trade = trade
                self.pending_entry_price = None
                self.pending_armed_tick = None
                self.trade_count += 1
                self.state.transition(TradeStateMachine.IN_TRADE)
                events.append(self._state_event(side=trade.side, entry_gate_open=False))
                events.append(
                    (
                        "strategy_decision",
                        {"kind": "entered", "ts": ts, "id": trade.id, "side": trade.side, "entry": trade.entry},
                    )
                )
                events.append(
                    (
                        "trade_opened",
                        {
                            "ts": ts,
                            "id": trade.id,
                            "side": trade.side,
                            "entry": trade.entry,
                            "take_profit": trade.take_profit,
                            "stop_loss": trade.stop_loss,
                            "wall_price": trade.entry,
                        },
                    )
                )
            elif self.tick_counter % 25 == 0:
                events.append(
                    (
                        "strategy_decision",
                        {
                            "kind": "armed_waiting_fill",
                            "ts": ts,
                            "entry_price": entry_price,
                            "last_price": price,
                        },
                    )
                )

        if self.open_trade is not None:
            events.extend(self._handle_exit_checks(price=price, ts=ts, microstate=microstate))

        return events

    def _handle_exit_checks(
        self, price: float, ts: float, microstate: dict[str, float]
    ) -> list[tuple[str, dict[str, object]]]:
        trade = self.open_trade
        if trade is None:
            return []

        pressure = float(microstate.get("pressure", 0.0))
        absorption = float(microstate.get("absorption", 0.0))
        ticks_open = self.tick_counter - trade.open_tick_count

        exit_reason = None
        exit_price = price

        if trade.side == "long":
            if price >= trade.take_profit:
                exit_reason = "tp"
                exit_price = trade.take_profit
            elif price <= trade.stop_loss:
                exit_reason = "sl"
                exit_price = trade.stop_loss
            elif pressure <= -self.pressure_flip_threshold and ticks_open >= self.min_ticks_before_flip_exit:
                exit_reason = "pressure_flip"
            elif absorption >= 0.82 and pressure < -0.05:
                exit_reason = "opposing_absorption"
            elif ticks_open >= self.max_stall_ticks:
                exit_reason = "stall"
        else:
            if price <= trade.take_profit:
                exit_reason = "tp"
                exit_price = trade.take_profit
            elif price >= trade.stop_loss:
                exit_reason = "sl"
                exit_price = trade.stop_loss
            elif pressure >= self.pressure_flip_threshold and ticks_open >= self.min_ticks_before_flip_exit:
                exit_reason = "pressure_flip"
            elif absorption >= 0.82 and pressure > 0.05:
                exit_reason = "opposing_absorption"
            elif ticks_open >= self.max_stall_ticks:
                exit_reason = "stall"

        if exit_reason is None:
            return []

        pnl_ticks = (
            (exit_price - trade.entry) / self.tick_size
            if trade.side == "long"
            else (trade.entry - exit_price) / self.tick_size
        )

        self.state.transition(TradeStateMachine.EXIT)
        exit_events: list[tuple[str, dict[str, object]]] = [
            (
                "strategy_decision",
                {"kind": "killed", "ts": ts, "id": trade.id, "reason": exit_reason},
            ),
            (
                "trade_closed",
                {
                    "ts": ts,
                    "id": trade.id,
                    "side": trade.side,
                    "entry": trade.entry,
                    "exit": exit_price,
                    "reason": exit_reason,
                    "pnl_ticks": round(pnl_ticks, 3),
                },
            ),
        ]
        self.open_trade = None
        self.current_setup = None
        self.pending_entry_price = None
        self.pending_armed_tick = None
        self.last_exit_tick = self.tick_counter
        self.state.transition(TradeStateMachine.IDLE)
        exit_events.append(self._state_event(side=None, entry_gate_open=False))
        return exit_events

    def _state_event(self, side: str | None, entry_gate_open: bool) -> tuple[str, dict[str, object]]:
        return (
            "strategy_state",
            {
                "state": self.state.state,
                "side": side,
                "entryGateOpen": entry_gate_open,
                "killFlags": [],
            },
        )
