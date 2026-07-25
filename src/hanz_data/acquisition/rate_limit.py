from __future__ import annotations

import threading
import time


class RateLimiter:
    def __init__(self, calls_per_second: float = 2.0) -> None:
        if calls_per_second <= 0:
            raise ValueError("calls_per_second must be positive")
        self.minimum_interval = 1.0 / calls_per_second
        self._lock = threading.Lock()
        self._last_call = 0.0

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            delay = self.minimum_interval - (now - self._last_call)
            if delay > 0:
                time.sleep(delay)
            self._last_call = time.monotonic()
