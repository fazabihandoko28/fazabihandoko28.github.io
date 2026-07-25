from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from hanz_data.models import Bar, MarketSeries
from hanz_data.providers.base import MarketDataProvider


@dataclass(frozen=True, slots=True)
class JsonFieldMap:
    timestamp: str = "timestamp"
    open: str = "open"
    high: str = "high"
    low: str = "low"
    close: str = "close"
    volume: str = "volume"


class HttpJsonProvider(MarketDataProvider):
    """Vendor-neutral REST provider configured by endpoint and response field map.

    Expected response shape: either a list of bars or a dict containing `bars_key`.
    Authentication headers and query parameters are injected from configuration.
    """

    def __init__(
        self,
        *,
        base_url: str,
        series_path: str,
        symbols_path: str | None = None,
        bars_key: str | None = None,
        symbols_key: str | None = None,
        field_map: JsonFieldMap | None = None,
        headers: dict[str, str] | None = None,
        default_query: dict[str, str] | None = None,
        timeout_seconds: float = 15.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.series_path = series_path
        self.symbols_path = symbols_path
        self.bars_key = bars_key
        self.symbols_key = symbols_key
        self.field_map = field_map or JsonFieldMap()
        self.headers = headers or {}
        self.default_query = default_query or {}
        self.timeout_seconds = timeout_seconds

    def _get(self, path: str, query: dict[str, str]) -> Any:
        merged = {**self.default_query, **query}
        url = f"{self.base_url}/{path.lstrip('/')}"
        if merged:
            url = f"{url}?{urlencode(merged)}"
        request = Request(url, headers=self.headers)
        with urlopen(request, timeout=self.timeout_seconds) as response:
            if response.status != 200:
                raise OSError(f"HTTP {response.status}")
            return json.loads(response.read().decode("utf-8"))

    def list_symbols(self, market: str) -> Iterable[str]:
        if not self.symbols_path:
            raise NotImplementedError("symbols_path is not configured")
        payload = self._get(self.symbols_path, {"market": market})
        if self.symbols_key:
            payload = payload[self.symbols_key]
        if not isinstance(payload, list):
            raise ValueError("symbol response must be a list")
        return [str(item["symbol"] if isinstance(item, dict) else item) for item in payload]

    def load_series(
        self,
        market: str,
        symbol: str,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> MarketSeries:
        path = self.series_path.format(market=market, symbol=symbol)
        query = {"market": market, "symbol": symbol}
        if start:
            query["start"] = start.isoformat()
        if end:
            query["end"] = end.isoformat()
        payload = self._get(path, query)
        if self.bars_key:
            payload = payload[self.bars_key]
        if not isinstance(payload, list):
            raise ValueError("bar response must be a list")
        bars: list[Bar] = []
        mapping = self.field_map
        for item in payload:
            timestamp_value = item[mapping.timestamp]
            timestamp = (
                datetime.fromtimestamp(float(timestamp_value))
                if isinstance(timestamp_value, (int, float))
                else datetime.fromisoformat(str(timestamp_value).replace("Z", "+00:00"))
            )
            bars.append(
                Bar(
                    market=market,
                    symbol=symbol,
                    timestamp=timestamp,
                    open=float(item[mapping.open]),
                    high=float(item[mapping.high]),
                    low=float(item[mapping.low]),
                    close=float(item[mapping.close]),
                    volume=float(item[mapping.volume]),
                )
            )
        return MarketSeries.from_iterable(symbol=symbol, market=market, bars=bars)
