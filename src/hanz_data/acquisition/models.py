from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from hanz_data.models import MarketSeries
from hanz_data.validation import ValidationReport


@dataclass(frozen=True, slots=True)
class AcquisitionRequest:
    market: str
    symbol: str
    start: datetime | None = None
    end: datetime | None = None
    minimum_bars: int = 60
    allow_cache: bool = True


@dataclass(slots=True)
class AcquisitionAudit:
    provider: str
    market: str
    symbol: str
    started_at: datetime
    finished_at: datetime | None = None
    attempts: int = 0
    cache_hit: bool = False
    normalized_symbol: str | None = None
    events: list[str] = field(default_factory=list)
    error: str | None = None


@dataclass(frozen=True, slots=True)
class AcquisitionResult:
    series: MarketSeries | None
    validation: ValidationReport | None
    audit: AcquisitionAudit

    @property
    def accepted(self) -> bool:
        return bool(self.series is not None and self.validation and self.validation.valid)
