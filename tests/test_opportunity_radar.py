from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from hanz_radar import (
    DeltaPolicy,
    DeltaScanner,
    OpportunityRadar,
    RadarHistory,
)
from hanz_realtime.models import SymbolState


class OpportunityRadarTests(unittest.TestCase):
    def now(self):
        return datetime(2026, 7, 27, 9, 0, 0, tzinfo=timezone.utc)

    def state(
        self,
        symbol="TINS",
        anomaly=75,
        change=1.2,
        velocity=0.2,
        spread=0.2,
        seconds_old=0,
    ):
        now = self.now()
        return SymbolState(
            symbol=symbol,
            market="BEI",
            last_price=3440,
            last_volume=10000,
            last_timestamp=now - timedelta(seconds=seconds_old),
            tick_count=10,
            cumulative_volume=5000,
            price_change_pct=change,
            spread_pct=spread,
            velocity=velocity,
            anomaly_score=anomaly,
        )

    def test_interesting_state_is_detected(self):
        scanner = DeltaScanner()
        self.assertTrue(scanner.is_interesting(self.state()))

    def test_stale_state_is_ignored(self):
        radar = OpportunityRadar()
        result = radar.evaluate([self.state(seconds_old=60)], now=self.now())
        self.assertEqual(len(result.active_signals), 0)

    def test_strong_state_becomes_ready(self):
        radar = OpportunityRadar()
        result = radar.evaluate([
            self.state(anomaly=95, change=2.5, velocity=1.0, spread=0.1)
        ], now=self.now())
        self.assertEqual(result.active_signals[0].status.value, "EKSEKUSI")

    def test_medium_state_becomes_prepare_or_early(self):
        radar = OpportunityRadar()
        result = radar.evaluate([
            self.state(anomaly=65, change=1.0, velocity=0.1, spread=0.3)
        ], now=self.now())
        self.assertIn(
            result.active_signals[0].status.value,
            {"SIAGA", "AWAL"},
        )

    def test_ranking_prefers_stronger_signal(self):
        radar = OpportunityRadar()
        result = radar.evaluate([
            self.state(symbol="AAA", anomaly=60, change=0.8, velocity=0.1),
            self.state(symbol="BBB", anomaly=90, change=2.0, velocity=0.5),
        ], now=self.now())
        self.assertEqual(result.active_signals[0].symbol, "BBB")

    def test_history_only_records_changes(self):
        history = RadarHistory()
        radar = OpportunityRadar(history=history)
        state = self.state()
        radar.evaluate([state], now=self.now())
        radar.evaluate([state], now=self.now())
        self.assertEqual(len(history.recent()), 1)

    def test_snapshot_is_compact(self):
        radar = OpportunityRadar()
        payload = radar.evaluate([self.state()], now=self.now()).to_dict()
        self.assertIn("RADAR", payload)
        self.assertIn("TOTAL", payload)
        self.assertLessEqual(
            len(payload["RADAR"][0]["status"].split()),
            2,
        )


if __name__ == "__main__":
    unittest.main()
