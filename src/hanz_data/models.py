from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Sequence


@dataclass(frozen=True, slots=True)
class Bar:
    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    market: str = "UNKNOWN"

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None:
            object.__setattr__(self, "timestamp", self.timestamp.replace(tzinfo=timezone.utc))


@dataclass(frozen=True, slots=True)
class MarketSeries:
    symbol: str
    market: str
    bars: tuple[Bar, ...]

    @classmethod
    def from_iterable(cls, symbol: str, market: str, bars: Iterable[Bar]) -> "MarketSeries":
        ordered = tuple(sorted(bars, key=lambda item: item.timestamp))
        return cls(symbol=symbol, market=market, bars=ordered)

    def closes(self) -> Sequence[float]:
        return [bar.close for bar in self.bars]

    def volumes(self) -> Sequence[float]:
        return [bar.volume for bar in self.bars]
