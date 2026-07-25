from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from hanz_data.acquisition.models import AcquisitionRequest, AcquisitionResult
from hanz_data.acquisition.service import AcquisitionService
from hanz_data.providers.registry import ProviderRegistry


@dataclass(frozen=True, slots=True)
class UniverseAcquisitionReport:
    market: str
    results: tuple[AcquisitionResult, ...]

    @property
    def accepted(self) -> tuple[AcquisitionResult, ...]:
        return tuple(result for result in self.results if result.accepted)

    @property
    def rejected(self) -> tuple[AcquisitionResult, ...]:
        return tuple(result for result in self.results if not result.accepted)


class UniverseAcquirer:
    def __init__(self, registry: ProviderRegistry, service_factory) -> None:
        self.registry = registry
        self.service_factory = service_factory

    def acquire_market(
        self,
        market: str,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        minimum_bars: int = 60,
    ) -> UniverseAcquisitionReport:
        provider = self.registry.get(market)
        service: AcquisitionService = self.service_factory(provider)
        symbols = tuple(provider.list_symbols(market))
        results = tuple(
            service.acquire(
                AcquisitionRequest(
                    market=market,
                    symbol=symbol,
                    start=start,
                    end=end,
                    minimum_bars=minimum_bars,
                )
            )
            for symbol in symbols
        )
        return UniverseAcquisitionReport(market=market.upper(), results=results)
