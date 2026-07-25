from __future__ import annotations

from bootstrap import PROJECT_ROOT  # noqa: F401
import io
import json
import sys
import types
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from hanz_data.providers.yahoo_provider import YahooFinanceProvider, YahooSymbol


class FakeIndex:
    def __init__(self, value):
        self.value = value

    def to_pydatetime(self):
        return self.value


class FakeColumns:
    nlevels = 1


class FakeFrame:
    empty = False
    columns = FakeColumns()

    def iterrows(self):
        rows = []
        for day in range(1, 65):
            rows.append((
                FakeIndex(datetime(2026, 1, min(day, 28), tzinfo=timezone.utc)),
                {"Open": 100 + day, "High": 102 + day, "Low": 99 + day, "Close": 101 + day, "Volume": 1_000_000 + day},
            ))
        return iter(rows)


class EmptyFrame:
    empty = True
    columns = FakeColumns()


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


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

    def test_chart_fallback_is_used_when_yfinance_is_empty(self):
        module = types.SimpleNamespace(download=lambda *args, **kwargs: EmptyFrame())
        original = sys.modules.get("yfinance")
        sys.modules["yfinance"] = module
        payload = {
            "chart": {"error": None, "result": [{
                "timestamp": [1704067200, 1704153600],
                "indicators": {"quote": [{
                    "open": [100, 101], "high": [103, 104], "low": [99, 100],
                    "close": [102, 103], "volume": [1000000, 1100000]
                }]},
            }]}
        }
        try:
            with patch("hanz_data.providers.yahoo_provider.urlopen", return_value=FakeResponse(payload)):
                provider = YahooFinanceProvider([YahooSymbol("BEI", "BBRI", "BBRI.JK")])
                series = provider.load_series("BEI", "BBRI")
                self.assertEqual(len(series.bars), 2)
                self.assertEqual(series.bars[-1].close, 103.0)
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
