import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from hanz_core import Signal
from hanz_data import Bar, MarketSeries, validate_series
from hanz_technical import build_technical_snapshot, ema, relative_volume, rsi


class TestTechnicalEngine(unittest.TestCase):
    def make_series(self):
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        bars = []
        for index in range(80):
            close = 100 + index * 0.8
            volume = 2_000_000 if index < 79 else 5_000_000
            bars.append(Bar("TEST", start + timedelta(days=index), close - 0.3, close + 0.5, close - 0.7, close, volume, "BEI"))
        return MarketSeries.from_iterable("TEST", "BEI", bars)

    def test_indicators_compute(self):
        values = list(range(1, 60))
        self.assertIsNotNone(ema(values, 20))
        self.assertEqual(rsi(values, 14), 100.0)
        volumes = [100.0] * 20 + [200.0]
        self.assertAlmostEqual(relative_volume(volumes, 20), 2.0)

    def test_snapshot_builds_auditable_evidence(self):
        series = self.make_series()
        report = validate_series(series, minimum_bars=60)
        snapshot = build_technical_snapshot(series, report)
        evidence = {item.name: item for item in snapshot.evidence}
        self.assertEqual(evidence["data_freshness"].signal, Signal.POSITIVE)
        self.assertEqual(evidence["price_structure"].signal, Signal.POSITIVE)
        self.assertIn("rvol20=", evidence["volume_confirmation"].detail)
