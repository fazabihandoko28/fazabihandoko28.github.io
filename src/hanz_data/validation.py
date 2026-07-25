from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Iterable

from .models import Bar, MarketSeries


@dataclass(slots=True)
class ValidationReport:
    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    duplicate_timestamps: int = 0
    missing_intervals: int = 0


def validate_series(
    series: MarketSeries,
    *,
    minimum_bars: int = 60,
    max_age: timedelta | None = None,
    now: datetime | None = None,
) -> ValidationReport:
    errors: list[str] = []
    warnings: list[str] = []
    seen: set[datetime] = set()
    duplicates = 0

    if len(series.bars) < minimum_bars:
        errors.append(f"insufficient_bars:{len(series.bars)}<{minimum_bars}")

    previous: Bar | None = None
    intervals: list[float] = []
    for bar in series.bars:
        if bar.timestamp in seen:
            duplicates += 1
        seen.add(bar.timestamp)

        if bar.open <= 0 or bar.high <= 0 or bar.low <= 0 or bar.close <= 0:
            errors.append(f"non_positive_price:{bar.timestamp.isoformat()}")
        if bar.volume < 0:
            errors.append(f"negative_volume:{bar.timestamp.isoformat()}")
        if bar.high < max(bar.open, bar.close, bar.low):
            errors.append(f"invalid_high:{bar.timestamp.isoformat()}")
        if bar.low > min(bar.open, bar.close, bar.high):
            errors.append(f"invalid_low:{bar.timestamp.isoformat()}")
        if previous is not None:
            delta = (bar.timestamp - previous.timestamp).total_seconds()
            if delta <= 0:
                errors.append(f"non_monotonic_time:{bar.timestamp.isoformat()}")
            else:
                intervals.append(delta)
        previous = bar

    if duplicates:
        errors.append(f"duplicate_timestamps:{duplicates}")

    missing_intervals = 0
    if intervals:
        sorted_intervals = sorted(intervals)
        median = sorted_intervals[len(sorted_intervals) // 2]
        if median > 0:
            missing_intervals = sum(delta > median * 3.1 for delta in intervals)
            if missing_intervals:
                warnings.append(f"large_time_gaps:{missing_intervals}")

    if max_age is not None and series.bars:
        current = now or datetime.now(timezone.utc)
        latest = series.bars[-1].timestamp.astimezone(timezone.utc)
        if current.astimezone(timezone.utc) - latest > max_age:
            errors.append(f"stale_data:{latest.isoformat()}")

    return ValidationReport(
        valid=not errors,
        errors=errors,
        warnings=warnings,
        duplicate_timestamps=duplicates,
        missing_intervals=missing_intervals,
    )
