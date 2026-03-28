from collections import deque


class Setup:
    """Buffers microstructure confluences (not trade signals)."""

    def __init__(self, on_confluence=None):
        self.WINDOW = 10

        self.confluences = deque(maxlen=50)
        self._on_confluence = on_confluence
        # Rolling window of per-bar price deltas (same sum/popleft pattern as Microstate.tps).
        self.delta = deque()
        self._delta_sum = 0.0
        self.avg_delta = 0.0
        self.bar_delta = 0.0

    def push_signal(self, label: str, time: float) -> None:
        entry = {"label": label, "time": time}
        self.confluences.append(entry)
        if self._on_confluence:
            self._on_confluence(label)

    def on_10th_tick(self, tick):
        # Net price change over the 10-tick bar (analogous to microstate price_delta over its window).
        self.bar_delta = float(tick["buy_volume"]) - float(tick["sell_volume"])
        self.delta.append(self.bar_delta)
        self._delta_sum += self.bar_delta
        if len(self.delta) > self.WINDOW:
            self._delta_sum -= self.delta.popleft()
        n = len(self.delta)
        self.avg_delta = self._delta_sum / n if n else 0.0
