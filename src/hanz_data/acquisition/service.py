from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

from hanz_data.providers.base import MarketDataProvider
from hanz_data.validation import validate_series

from .cache import FileSeriesCache
from .models import AcquisitionAudit, AcquisitionRequest, AcquisitionResult
from .rate_limit import RateLimiter
from .retry import execute_with_retry
from .symbols import SymbolNormalizer


class AcquisitionService:
    """Fetch -> normalize -> validate -> cache. Invalid data never reaches intelligence engines."""

    def __init__(
        self,
        provider: MarketDataProvider,
        *,
        cache: FileSeriesCache | None = None,
        normalizer: SymbolNormalizer | None = None,
        rate_limiter: RateLimiter | None = None,
        attempts: int = 3,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.provider = provider
        self.cache = cache
        self.normalizer = normalizer or SymbolNormalizer()
        self.rate_limiter = rate_limiter or RateLimiter(10.0)
        self.attempts = attempts
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def acquire(self, request: AcquisitionRequest) -> AcquisitionResult:
        audit = AcquisitionAudit(
            provider=type(self.provider).__name__,
            market=request.market.upper(),
            symbol=request.symbol.upper(),
            started_at=self.clock(),
        )
        normalized = self.normalizer.canonical(request.market, request.symbol)
        audit.normalized_symbol = normalized

        if request.allow_cache and self.cache:
            cached = self.cache.get(request.market, normalized, request.start, request.end)
            if cached is not None:
                report = validate_series(cached, minimum_bars=request.minimum_bars)
                audit.events.append("cache_read")
                if report.valid:
                    audit.cache_hit = True
                    audit.finished_at = self.clock()
                    return AcquisitionResult(cached, report, audit)
                audit.events.append("cache_rejected_by_validation")

        def operation():
            self.rate_limiter.wait()
            return self.provider.load_series(
                request.market,
                normalized,
                start=request.start,
                end=request.end,
            )

        def on_attempt(number: int) -> None:
            audit.attempts = number
            audit.events.append(f"provider_attempt:{number}")

        try:
            series = execute_with_retry(operation, attempts=self.attempts, on_attempt=on_attempt)
            report = validate_series(series, minimum_bars=request.minimum_bars)
            audit.events.append("validation_complete")
            if report.valid and self.cache:
                self.cache.put(series, request.start, request.end)
                audit.events.append("cache_write")
            if not report.valid:
                audit.events.append("data_rejected")
            audit.finished_at = self.clock()
            return AcquisitionResult(series, report, audit)
        except Exception as exc:  # boundary: acquisition errors are converted into auditable results
            audit.error = f"{type(exc).__name__}:{exc}"
            audit.events.append("provider_failed")
            audit.finished_at = self.clock()
            return AcquisitionResult(None, None, audit)
