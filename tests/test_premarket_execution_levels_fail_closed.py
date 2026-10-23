"""Regression: exploratory PMR80 cannot publish trade levels from spoofed labels."""
import unittest

from hanz_app import premarket_bullish_predictor as pmr


class FakeEngine:
    def __init__(self):
        self.published = None
        candles = [
            {"time": "2026-10-23", "close": 100.0, "volume": 100_000_000}
            for _ in range(21)
        ]
        self.charts = [
            {"ticker": ticker, "source_bar_at": "2026-10-23", "candles": candles}
            for ticker in ("BBCA", "BBRI", "BMRI", "TLKM", "ASII")
        ]
        self.monitor = [
            {
                "ticker": row["ticker"],
                "state": "SETUP_READY",
                "daily_bar_at": "2026-10-23T00:00:00+00:00",
                "risk_gate": "ELIGIBLE",
                "entry_status": "ENTRY_ZONE",
                "entry_price": 98,
                "entry_low": 95,
                "entry_high": 99,
                "stop_loss": 90,
                "target_1": 110,
                "target_2": 120,
            }
            for row in self.charts
        ]

    def supabase_request(self, method, endpoint, **kwargs):
        if method == "GET" and "hanz_swing_chart_data" in endpoint:
            return self.charts
        if method == "GET" and "hanz_swing_signal_monitor" in endpoint:
            return self.monitor
        if method == "POST" and "hanz_premarket_bullish_current" in endpoint:
            self.published = kwargs["payload"]
            return []
        raise AssertionError(f"Unexpected request: {method} {endpoint}")

    def now_iso(self):
        return "2026-10-23T10:00:00Z"


class PMR80ExecutionGuardTests(unittest.TestCase):
    def test_spoofed_eligible_entry_zone_cannot_publish_execution_levels(self):
        engine = FakeEngine()
        result = pmr.publish(engine)
        self.assertEqual(result["published"], 5)
        self.assertEqual(len(engine.published), 5)
        for row in engine.published:
            self.assertEqual(row["entry_status"], "UNVALIDATED_LEVELS")
            for field in ("entry_price", "entry_low", "entry_high",
                          "stop_loss", "target_1", "target_2"):
                self.assertIsNone(row[field], f"{row['ticker']} leaked {field}")
            self.assertTrue(row["prediction_label"].startswith("RADAR_"))


if __name__ == "__main__":
    unittest.main()
