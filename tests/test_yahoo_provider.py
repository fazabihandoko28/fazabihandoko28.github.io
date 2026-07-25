from __future__ import annotations

import sys
import types
import unittest
from datetime import datetime, timezone

from hanz_data.providers.yahoo_provider import YahooFinanceProvider, YahooSymbol


class FakeIndex:
    def __init__(self, value):
        self.value = value

    def to_pydatetime(self):
        return self.value


class FakeFrame:
    empty = False

    def iterrows(self):
        rows = []
        for day in range(1, 65):
            rows.append((
                FakeIndex(datetime(2026, 1, min(day, 28), tzinfo=timezone.utc)),
                {"Open": 100 + day, "High": 102 + day, "Low": 99 + day, "Close": 101 + day, "Volume": 1_000_000 + day},
            ))
        return iter(rows)


class YahooProviderTests(unittest.TestCase):
    def test_download_is_normalized_to_market_series(self):
        module = types.SimpleNamespace(download=lambda *args, **kwargs: FakeFrame())
        original = sys.modules.get("yfinance")
        sys.modules["yfinance"] = module
        try:
            provider = YahooFinanceProvider([YahooSymbol("BEI", "BBRI", "BBRI.JK")])
            series = provider.load_series("BEI", "BBRI")
            self.assertEqual(series.symbol, "BBRI")
            self.assertEqual(series.market, "BEI")
            self.assertEqual(len(series.bars), 64)
            self.assertEqual(series.bars[-1].close, 165.0)
        finally:
            if original is None:
                del sys.modules["yfinance"]
            else:
                sys.modules["yfinance"] = original

    def test_unknown_mapping_is_rejected(self):
        provider = YahooFinanceProvider([YahooSymbol("BEI", "BBRI", "BBRI.JK")])
        with self.assertRaises(Exception):
            provider.load_series("BEI", "BBCA")


if __name__ == "__main__":
    unittest.main()
