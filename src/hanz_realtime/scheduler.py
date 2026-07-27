from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True)
class SchedulePolicy:
    fast_seconds: int = 1
    rank_seconds: int = 15
    candle_seconds: int = 60
    regime_seconds: int = 300


class SmartScheduler:
    def __init__(self, policy: SchedulePolicy | None = None) -> None:
        self.policy = policy or SchedulePolicy()
        self._last_run: dict[str, datetime] = {}

    def due(self, task: str, now: datetime) -> bool:
        interval = self._interval(task)
        previous = self._last_run.get(task)
        if previous is None or now - previous >= interval:
            self._last_run[task] = now
            return True
        return False

    def _interval(self, task: str) -> timedelta:
        mapping = {
            "fast": self.policy.fast_seconds,
            "rank": self.policy.rank_seconds,
            "candle": self.policy.candle_seconds,
            "regime": self.policy.regime_seconds,
        }
        if task not in mapping:
            raise KeyError(f"Unknown task: {task}")
        return timedelta(seconds=mapping[task])
