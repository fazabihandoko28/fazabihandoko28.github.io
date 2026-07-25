from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

from hanz_data.models import Bar, MarketSeries
from hanz_data.providers.base import MarketDataProvider


class YahooProviderError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class YahooSymbol:
    market: str
    symbol: str
    yahoo_ticker: str


class YahooFinanceProvider(MarketDataProvider):
    """Free research adapter backed by yfinance/Yahoo public endpoints.

    This adapter is deliberately marked RESEARCH_ONLY. It is not an official
    exchange feed, is delayed, and may have coverage gaps. Every returned series
    records its source so the decision engine can audit provenance.
    """

    source_name = "YAHOO_FINANCE_RESEARCH_ONLY"

    def __init__(
        self,
        symbols: Iterable[YahooSymbol],
        *,
        period: str = "1y",
        interval: str = "1d",
        auto_adjust: bool = False,
        repair: bool = True,
    ) -> None:
        self._symbols = tuple(symbols)
        self.period = period
        self.interval = interval
        self.auto_adjust = auto_adjust
        self.repair = repair

    def list_symbols(self, market: str) -> list[str]:
        market = market.upper()
        return sorted(item.symbol for item in self._symbols if item.market.upper() == market)

    def _lookup(self, market: str, symbol: str) -> YahooSymbol:
        for item in self._symbols:
            if item.market.upper() == market.upper() and item.symbol.upper() == symbol.upper():
                return item
        raise YahooProviderError(f"No Yahoo mapping configured for {market}:{symbol}")

    def load_series(
        self,
        market: str,
        symbol: str,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> MarketSeries:
        mapping = self._lookup(market, symbol)
        try:
            import yfinance as yf
        except ImportError as exc:  # pragma: no cover
            raise YahooProviderError("Install project dependencies before using Yahoo provider") from exc

        frame = yf.download(
            mapping.yahoo_ticker,
            period=None if start or end else self.period,
            start=start,
            end=end,
            interval=self.interval,
            auto_adjust=self.auto_adjust,
            repair=self.repair,
            progress=False,
            threads=False,
            timeout=20,
            multi_level_index=False,
        )
        if frame is None or frame.empty:
            raise YahooProviderError(f"No data returned for {mapping.yahoo_ticker}")

        bars: list[Bar] = []
        for index, row in frame.iterrows():
            timestamp = index.to_pydatetime() if hasattr(index, "to_pydatetime") else index
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)
            bars.append(
                Bar(
                    symbol=symbol.upper(),
                    market=market.upper(),
                    timestamp=timestamp,
                    open=float(row["Open"]),
                    high=float(row["High"]),
                    low=float(row["Low"]),
                    close=float(row["Close"]),
                    volume=float(row["Volume"]),
                )
            )
        if not bars:
            raise YahooProviderError(f"No valid OHLCV bars for {mapping.yahoo_ticker}")
        return MarketSeries.from_iterable(
            market=market.upper(),
            symbol=symbol.upper(),
            bars=bars,
        )
