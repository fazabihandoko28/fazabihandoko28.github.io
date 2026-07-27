from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum
from typing import Any


class RadarStatus(str, Enum):
    EARLY = "AWAL"
    PREPARE = "SIAGA"
    READY = "EKSEKUSI"
    HOLD = "TAHAN"
    RELEASE = "LEPAS"
    SELL = "JUAL"
    SKIP = "LEWATI"


@dataclass(frozen=True)
class RadarSignal:
    symbol: str
    market: str
    status: RadarStatus
    evidence: int
    anomaly: float
    risk: str
    price: float | None
    trigger: str | None
    reason: str
    timestamp: datetime

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        data["timestamp"] = self.timestamp.isoformat()
        return data


@dataclass(frozen=True)
class RadarSnapshot:
    generated_at: datetime
    total_symbols: int
    active_signals: tuple[RadarSignal, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "generated_at": self.generated_at.isoformat(),
            "TOTAL": self.total_symbols,
            "RADAR": [signal.to_dict() for signal in self.active_signals],
        }
