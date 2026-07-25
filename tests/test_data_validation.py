import os
import sys
import unittest
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from hanz_data import Bar, MarketSeries, validate_series


class TestDataValidation(unittest.TestCase):
    def test_valid_series(self):
        bars = [
            Bar("TEST", datetime(2026, 1, day, tzinfo=timezone.utc), 100, 102, 99, 101, 1000, "BEI")
            for day in range(1, 29)
        ]
        report = validate_series(MarketSeries.from_iterable("TEST", "BEI", bars), minimum_bars=20)
        self.assertTrue(report.valid)

    def test_invalid_ohlc(self):
        bars = [Bar("TEST", datetime(2026, 1, 1, tzinfo=timezone.utc), 100, 99, 98, 101, 1000, "BEI")]
        report = validate_series(MarketSeries.from_iterable("TEST", "BEI", bars), minimum_bars=1)
        self.assertFalse(report.valid)
        self.assertTrue(any(item.startswith("invalid_high") for item in report.errors))
