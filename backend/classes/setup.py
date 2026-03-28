from collections import deque


class Setup:
    """Buffers microstructure confluences (not trade signals)."""

    def __init__(self, on_confluence=None):
        self.confluences = deque(maxlen=50)
        self._on_confluence = on_confluence

    def push_signal(self, label: str, time: float) -> None:
        entry = {"label": label, "time": time}
        self.confluences.append(entry)
        if self._on_confluence:
            self._on_confluence(label)
