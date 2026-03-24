from __future__ import annotations


class TradeStateMachine:
    IDLE = "IDLE"
    SETUP_FOUND = "SETUP_FOUND"
    WAITING_TRIGGER = "WAITING_TRIGGER"
    IN_TRADE = "IN_TRADE"
    EXIT = "EXIT"

    def __init__(self) -> None:
        self.state = self.IDLE

    def transition(self, next_state: str) -> str:
        self.state = next_state
        return self.state
