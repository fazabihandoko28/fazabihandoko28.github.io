from __future__ import annotations

from bootstrap import PROJECT_ROOT  # noqa: F401

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from hanz_data.acquisition import AcquisitionRequest, AcquisitionService, FileSeriesCache
from hanz_data.acquisition.symbols import SymbolNormalizer
from hanz_data.models import Bar, MarketSeries
from hanz_data.providers.base import MarketDataProvider


class FakeProvider(MarketDataProvider):
    def __init__(self, *, fail_times: int = 0, invalid: bool = False) -> None:
        self.fail_times = fail_times
        self.invalid = invalid
        self.calls = 0

    def list_symbols(self, market: str):
        return ["BBCA", "PTBA"]

    def load_series(self, market, symbol, *, start=None, end=None):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise OSError("temporary")
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        bars = []
        for index in range(80):
            close = 100 + index
            bars.append(
                Bar(
                    market=market,
                    symbol=symbol,
                    timestamp=now + timedelta(days=index),
                    open=close - 1,
                    high=close + 1,
                    low=close - 2,
                    close=close,
                    volume=-1 if self.invalid and index == 10 else 1000 + index,
                )
            )
        return MarketSeries.from_iterable(symbol=symbol, market=market, bars=bars)


class AcquisitionTests(unittest.TestCase):
    def test_retry_then_accept(self):
        provider = FakeProvider(fail_times=1)
        service = AcquisitionService(provider, attempts=3)
        result = service.acquire(AcquisitionRequest("BEI", "BBCA", minimum_bars=60))
        self.assertTrue(result.accepted)
        self.assertEqual(result.audit.attempts, 2)

    def test_invalid_data_is_rejected(self):
        provider = FakeProvider(invalid=True)
        service = AcquisitionService(provider)
        result = service.acquire(AcquisitionRequest("BEI", "BBCA", minimum_bars=60))
        self.assertFalse(result.accepted)
        self.assertIn("data_rejected", result.audit.events)

    def test_cache_avoids_second_provider_call(self):
        provider = FakeProvider()
        with tempfile.TemporaryDirectory() as directory:
            service = AcquisitionService(provider, cache=FileSeriesCache(directory))
            request = AcquisitionRequest("BEI", "BBCA", minimum_bars=60)
            first = service.acquire(request)
            second = service.acquire(request)
            self.assertTrue(first.accepted)
            self.assertTrue(second.accepted)
            self.assertTrue(second.audit.cache_hit)
            self.assertEqual(provider.calls, 1)

    def test_market_suffix_normalization(self):
        normalizer = SymbolNormalizer({"BEI": ".JK", "ADX": ".AD"})
        self.assertEqual(normalizer.canonical("BEI", "bbca"), "BBCA.JK")
        self.assertEqual(normalizer.canonical("ADX", "aldar.ad"), "ALDAR.AD")


if __name__ == "__main__":
    unittest.main()
