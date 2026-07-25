from __future__ import annotations

from hanz_data.providers.base import MarketDataProvider


class ProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, MarketDataProvider] = {}

    def register(self, market: str, provider: MarketDataProvider) -> None:
        key = market.upper().strip()
        if not key:
            raise ValueError("market cannot be blank")
        self._providers[key] = provider

    def get(self, market: str) -> MarketDataProvider:
        key = market.upper().strip()
        try:
            return self._providers[key]
        except KeyError as exc:
            raise KeyError(f"no provider registered for market {key}") from exc

    def markets(self) -> tuple[str, ...]:
        return tuple(sorted(self._providers))
