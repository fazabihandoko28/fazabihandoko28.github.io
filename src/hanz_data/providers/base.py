from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Iterable

from hanz_data.models import MarketSeries


class MarketDataProvider(ABC):
    """Provider contract. Engines depend on this interface, never on a vendor."""

    @abstractmethod
    def list_symbols(self, market: str) -> Iterable[str]:
        raise NotImplementedError

    @abstractmethod
    def load_series(
        self,
        market: str,
        symbol: str,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> MarketSeries:
        raise NotImplementedError
