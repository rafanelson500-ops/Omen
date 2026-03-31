from numba import njit

class Strategy:
    def __init__(self):
        self.TICK_COOLDOWN = 10
        self.ENTRY_TYPES = {
            "OVEREXTENSION": {
                "ticks_since_overextended": 0,
            }
        }

        self.status = "READY"
        self.cooldown_ticks = 0

    def on_tick(self, tick):
        match self.status:
            case "READY": # Looking for entries
                self.entry_types["OVEREXTENSION"]["ticks_since_overextended"] += 1

            case "IN_TRADE":
                self.entry_types["OVEREXTENSION"]["ticks_since_overextended"] += 1

            case "COOLDOWN":
                self.cooldown_ticks += 1
                if self.cooldown_ticks >= self.TICK_COOLDOWN:
                    self.status = "READY"
                    self.cooldown_ticks = 0