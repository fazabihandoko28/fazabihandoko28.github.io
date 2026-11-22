"""Same-snapshot production replacement probe regression."""
import unittest
from unittest.mock import patch
from hanz_app.research.g2_production_top5 import build_report


class ReplacementProbeTests(unittest.TestCase):
    @patch("hanz_app.research.g2_production_top5.select_monitor_top_five")
    def test_candidate_replacement_from_same_snapshot(self, select):
        def select_fixture(rows, *, as_of):
            tickers = {row["ticker"] for row in rows}
            selected = [ticker for ticker in ("AAA", "BBB", "CCC") if ticker in tickers][:2]
            return {"selected": selected, "selection_complete": False,
                    "vacant_slots": 5 - len(selected)}
        select.side_effect = select_fixture
        rows = [{"ticker": "AAA"}, {"ticker": "BBB"}, {"ticker": "CCC"}]
        report = build_report(rows, as_of="2026-11-20", generated_at="2026-11-21T00:00:00Z")
        self.assertTrue(report["replacement_probe"]["verified"])
        self.assertEqual(report["replacement_probe"]["replacement_ticker"], "CCC")
        self.assertEqual(report["candidate_replacement_evidence"], "COUNTERFACTUAL_REPLACEMENT_VERIFIED")
        self.assertEqual(len(report["replacement_probes"]), 2)
        self.assertEqual([p["removed_ticker"] for p in report["replacement_probes"]], ["AAA", "BBB"])
        self.assertEqual(report["replacement_probes"][1]["replacement_ticker"], "CCC")
        self.assertEqual(select.call_count, 3)
        self.assertFalse(report["historical_point_in_time_oos_verified"])

    @patch("hanz_app.research.g2_production_top5.select_monitor_top_five")
    def test_no_replacement_does_not_claim_success(self, select):
        select.side_effect = [
            {"selected": ["AAA"], "selection_complete": False, "vacant_slots": 4},
            {"selected": [], "selection_complete": False, "vacant_slots": 5},
        ]
        report = build_report([{"ticker": "AAA"}], as_of="2026-11-20", generated_at="2026-11-21T00:00:00Z")
        self.assertFalse(report["replacement_probe"]["verified"])
        self.assertIsNone(report["replacement_probe"]["replacement_ticker"])


if __name__ == "__main__":
    unittest.main()
