import unittest
from datetime import date, timedelta

from hanz_app import premarket_bullish_predictor as pmr


class FakeEngine:
    def __init__(self, risk_gate="MONITOR", verified=False, actionable=False):
        start = date(2026, 9, 19)
        candles = [
            {"time": (start + timedelta(days=i)).isoformat(), "close": 100, "volume": 100_000_000}
            for i in range(25)
        ]
        self.charts = [
            {"ticker": f"T{i:03d}", "source_bar_at": "2026-10-13", "candles": candles}
            for i in range(5)
        ]
        self.monitor = [
            {
                "ticker": f"T{i:03d}", "state": "SETUP_READY",
                "daily_bar_at": "2026-10-13", "risk_gate": risk_gate,
                "entry_status": "ENTRY_ZONE", "entry_price": 100,
                "entry_low": 98, "entry_high": 101, "stop_loss": 90,
                "target_1": 110, "target_2": 120,
                "risk_validation": {
                    "data_same_session_verified": verified,
                    "actionable": actionable,
                },
            }
            for i in range(5)
        ]
        self.published = None

    def supabase_request(self, method, endpoint, payload=None, prefer=None):
        if method == "GET":
            return self.charts if endpoint.startswith("hanz_swing_chart_data") else self.monitor
        if method == "POST":
            self.published = payload
            return []
        raise AssertionError((method, endpoint))

    def now_iso(self):
        return "2026-10-13T09:32:00+00:00"


class Pmr80CanonicalGateTest(unittest.TestCase):
    def test_unverified_data_hides_levels(self):
        engine = FakeEngine(risk_gate="ELIGIBLE", verified=False, actionable=True)
        self.assertEqual(pmr.publish(engine)["published"], 5)
        self.assertTrue(all(row["entry_status"] == "UNVALIDATED_LEVELS" for row in engine.published))
        self.assertTrue(all(row["stop_loss"] is None for row in engine.published))

    def test_monitor_gate_hides_levels_even_if_verified(self):
        engine = FakeEngine(risk_gate="MONITOR", verified=True, actionable=True)
        self.assertEqual(pmr.publish(engine)["published"], 5)
        self.assertTrue(all(row["entry_low"] is None for row in engine.published))

    def test_incomplete_top_five_preserves_previous(self):
        engine = FakeEngine()
        engine.charts = engine.charts[:4]
        self.assertEqual(pmr.publish(engine)["published"], 0)
        self.assertIsNone(engine.published)


if __name__ == "__main__":
    unittest.main()
