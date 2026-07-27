from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Deque


@dataclass(frozen=True)
class PricePoint:
    timestamp: datetime
    price: float
    volume: float


class RollingWindow:
    def __init__(self, max_points: int = 300, max_age_seconds: int = 300) -> None:
        self.max_points = max_points
        self.max_age = timedelta(seconds=max_age_seconds)
        self._points: Deque[PricePoint] = deque(maxlen=max_points)

    def add(self, point: PricePoint) -> None:
        self._points.append(point)
        self._trim(point.timestamp)

    def _trim(self, now: datetime) -> None:
        while self._points and now - self._points[0].timestamp > self.max_age:
            self._points.popleft()

    def prices(self) -> list[float]:
        return [point.price for point in self._points]

    def volumes(self) -> list[float]:
        return [point.volume for point in self._points]

    def first(self) -> PricePoint | None:
        return self._points[0] if self._points else None

    def last(self) -> PricePoint | None:
        return self._points[-1] if self._points else None

    def __len__(self) -> int:
        return len(self._points)
