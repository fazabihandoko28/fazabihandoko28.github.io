from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class Tick:
    symbol: str
    market: str
    price: float
    volume: float
    timestamp: datetime
    bid: float | None = None
    ask: float | None = None
    source: str = "UNKNOWN"


@dataclass
class SymbolState:
    symbol: str
    market: str
    last_price: float | None = None
    last_volume: float = 0.0
    last_timestamp: datetime | None = None
    tick_count: int = 0
    cumulative_volume: float = 0.0
    price_change_pct: float = 0.0
    spread_pct: float | None = None
    velocity: float = 0.0
    anomaly_score: float = 0.0
    dirty_flags: set[str] = field(default_factory=set)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class QueueItem:
    symbol: str
    market: str
    score: float
    reason: str
    updated_at: datetime
