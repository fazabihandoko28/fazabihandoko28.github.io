from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime

from .models import RadarSignal


@dataclass(frozen=True)
class StatusChange:
    symbol: str
    market: str
    old_status: str | None
    new_status: str
    timestamp: datetime


class RadarHistory:
    def __init__(self, max_events: int = 1000) -> None:
        self._last_status: dict[tuple[str, str], str] = {}
        self._events: deque[StatusChange] = deque(maxlen=max_events)

    def record(self, signal: RadarSignal) -> StatusChange | None:
        key = (signal.market, signal.symbol)
        old = self._last_status.get(key)
        new = signal.status.value

        if old == new:
            return None

        change = StatusChange(
            symbol=signal.symbol,
            market=signal.market,
            old_status=old,
            new_status=new,
            timestamp=signal.timestamp,
        )
        self._last_status[key] = new
        self._events.append(change)
        return change

    def recent(self, limit: int = 50) -> list[StatusChange]:
        return list(self._events)[-limit:]
