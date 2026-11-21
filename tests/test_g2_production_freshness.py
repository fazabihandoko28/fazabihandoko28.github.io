"""Production evidence diagnostics: timestamps never imply verified live freshness."""
import unittest
from hanz_app.research.g2_production_top5 import build_report


class ProductionFreshnessTests(unittest.TestCase):
    def test_empty_eligible_set_reports_shortfall_and_timestamps(self):
        rows = [
            {"ticker": "AAA", "updated_at": "2026-11-20T09:00:00Z",
             "risk_validation": {"hanz_action": "AVOID"}},
            {"ticker": "BBB", "updated_at": "not-a-timestamp",
             "risk_validation": {"hanz_action": "AVOID"}},
        ]
        result = build_report(rows, as_of="2026-11-21T03:00:00Z",
                              generated_at="2026-11-21T03:00:00Z")
        self.assertEqual(result["source_latest_updated_at"], "2026-11-20T09:00:00+00:00")
        self.assertEqual(result["source_rows_without_valid_timestamp"], 1)
        self.assertEqual(result["candidate_shortfall"], 5)
        self.assertEqual(result["candidate_replacement_evidence"], "INSUFFICIENT_ELIGIBLE_CANDIDATES")
        self.assertFalse(result["market_session_freshness_verified"])
        self.assertFalse(result["production_top5_complete"])
        self.assertFalse(result["buy_authorized"])

    def test_future_snapshot_never_proves_freshness(self):
        rows = [{"ticker": "AAA", "updated_at": "2026-11-22T10:00:00Z",
                 "risk_validation": {"hanz_action": "AVOID"}}]
        result = build_report(rows, as_of="2026-11-21T03:00:00Z",
                              generated_at="2026-11-21T03:00:00Z")
        self.assertEqual(result["selected"], [])
        self.assertFalse(result["market_session_freshness_verified"])


if __name__ == "__main__":
    unittest.main()
