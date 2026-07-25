from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

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
    """Research-only Yahoo adapter with two acquisition paths.

    Primary path uses yfinance. If that path raises, returns no rows, or emits
    malformed rows, HANZ falls back to Yahoo's public chart response. Both are
    delayed, non-official research sources and are blocked from live execution.
    """

    source_name = "YAHOO_FINANCE_RESEARCH_ONLY"

    def __init__(
        self,
        symbols: Iterable[YahooSymbol],
        *,
        period: str = "1y",
        interval: str = "1d",
        auto_adjust: bool = False,
        repair: bool = False,
        timeout: int = 25,
    ) -> None:
        self._symbols = tuple(symbols)
        self.period = period
        self.interval = interval
        self.auto_adjust = auto_adjust
        self.repair = repair
        self.timeout = timeout

    def list_symbols(self, market: str) -> list[str]:
        market = market.upper()
        return sorted(item.symbol for item in self._symbols if item.market.upper() == market)

    def _lookup(self, market: str, symbol: str) -> YahooSymbol:
        for item in self._symbols:
            if item.market.upper() == market.upper() and item.symbol.upper() == symbol.upper():
                return item
        raise YahooProviderError(f"No Yahoo mapping configured for {market}:{symbol}")

    @staticmethod
    def _timestamp(value: object) -> datetime:
        timestamp = value.to_pydatetime() if hasattr(value, "to_pydatetime") else value
        if not isinstance(timestamp, datetime):
            raise ValueError(f"Unsupported timestamp type: {type(timestamp).__name__}")
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        return timestamp

    @staticmethod
    def _number(value: object, field: str) -> float:
        # pandas can return a one-value Series for some yfinance versions.
        if hasattr(value, "iloc"):
            if len(value) == 0:
                raise ValueError(f"Empty {field}")
            value = value.iloc[0]
        number = float(value)
        if number != number:  # NaN
            raise ValueError(f"NaN {field}")
        return number

    def _load_yfinance(self, mapping: YahooSymbol, market: str, symbol: str, start, end) -> MarketSeries:
        try:
            import yfinance as yf
        except ImportError as exc:  # pragma: no cover
            raise YahooProviderError("yfinance is not installed") from exc

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
            timeout=self.timeout,
            group_by="column",
        )
        if frame is None or frame.empty:
            raise YahooProviderError(f"yfinance returned no data for {mapping.yahoo_ticker}")

        # Flatten MultiIndex columns used by recent yfinance releases.
        if hasattr(frame.columns, "nlevels") and frame.columns.nlevels > 1:
            frame.columns = frame.columns.get_level_values(0)

        bars: list[Bar] = []
        row_errors = 0
        for index, row in frame.iterrows():
            try:
                bars.append(
                    Bar(
                        symbol=symbol.upper(),
                        market=market.upper(),
                        timestamp=self._timestamp(index),
                        open=self._number(row["Open"], "Open"),
                        high=self._number(row["High"], "High"),
                        low=self._number(row["Low"], "Low"),
                        close=self._number(row["Close"], "Close"),
                        volume=self._number(row["Volume"], "Volume"),
                    )
                )
            except (KeyError, TypeError, ValueError, IndexError):
                row_errors += 1
        if not bars:
            raise YahooProviderError(
                f"yfinance produced no valid OHLCV bars for {mapping.yahoo_ticker}; invalid_rows={row_errors}"
            )
        return MarketSeries.from_iterable(market=market.upper(), symbol=symbol.upper(), bars=bars)

    def _chart_url(self, ticker: str) -> str:
        params = urlencode({
            "range": self.period,
            "interval": self.interval,
            "events": "div,splits",
            "includeAdjustedClose": "true",
        })
        return f"https://query1.finance.yahoo.com/v8/finance/chart/{quote(ticker, safe='')}?{params}"

    def _load_chart(self, mapping: YahooSymbol, market: str, symbol: str) -> MarketSeries:
        request = Request(
            self._chart_url(mapping.yahoo_ticker),
            headers={
                "User-Agent": "Mozilla/5.0 HANZ-Intelligence-Research/0.8",
                "Accept": "application/json,text/plain,*/*",
            },
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise YahooProviderError(f"Yahoo chart request failed for {mapping.yahoo_ticker}: {exc}") from exc

        chart = payload.get("chart") or {}
        error = chart.get("error")
        if error:
            raise YahooProviderError(f"Yahoo chart error for {mapping.yahoo_ticker}: {error}")
        results = chart.get("result") or []
        if not results:
            raise YahooProviderError(f"Yahoo chart returned no result for {mapping.yahoo_ticker}")
        result = results[0]
        timestamps = result.get("timestamp") or []
        indicators = result.get("indicators") or {}
        quotes = indicators.get("quote") or []
        quote_data = quotes[0] if quotes else {}

        bars: list[Bar] = []
        invalid_rows = 0
        for idx, epoch in enumerate(timestamps):
            try:
                values = {
                    field: (quote_data.get(field) or [])[idx]
                    for field in ("open", "high", "low", "close", "volume")
                }
                if any(value is None for value in values.values()):
                    invalid_rows += 1
                    continue
                bars.append(
                    Bar(
                        symbol=symbol.upper(),
                        market=market.upper(),
                        timestamp=datetime.fromtimestamp(int(epoch), tz=timezone.utc),
                        open=float(values["open"]),
                        high=float(values["high"]),
                        low=float(values["low"]),
                        close=float(values["close"]),
                        volume=float(values["volume"]),
                    )
                )
            except (IndexError, TypeError, ValueError):
                invalid_rows += 1
        if not bars:
            raise YahooProviderError(
                f"Yahoo chart produced no valid OHLCV bars for {mapping.yahoo_ticker}; invalid_rows={invalid_rows}"
            )
        return MarketSeries.from_iterable(market=market.upper(), symbol=symbol.upper(), bars=bars)

    def load_series(
        self,
        market: str,
        symbol: str,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> MarketSeries:
        mapping = self._lookup(market, symbol)
        primary_error: Exception | None = None
        try:
            return self._load_yfinance(mapping, market, symbol, start, end)
        except Exception as exc:  # isolated provider fallback
            primary_error = exc

        try:
            return self._load_chart(mapping, market, symbol)
        except Exception as fallback_error:
            raise YahooProviderError(
                f"Both Yahoo acquisition paths failed for {mapping.yahoo_ticker}. "
                f"yfinance={primary_error}; chart={fallback_error}"
            ) from fallback_error
