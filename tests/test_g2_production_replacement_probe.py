"""Same-snapshot production replacement probe regression."""
import unittest
from unittest.mock import patch
from hanz_app.research.g2_production_top5 import build_report


class ReplacementProbeTests(unittest.TestCase):
    @patch("hanz_app.research.g2_production_top5.select_monitor_top_five")
    def test_candidate_replacement_from_same_snapshot(self, select):
        select.side_effect = [
            {"selected": ["AAA", "BBB"], "selection_complete": False, "vacant_slots": 3},
            {"selected": ["BBB", "CCC"], "selection_complete": False, "vacant_slots": 3},
        ]
        rows = [{"ticker": "AAA"}, {"ticker": "BBB"}, {"ticker": "CCC"}]
        report = build_report(rows, as_of="2026-11-20", generated_at="2026-11-21T00:00:00Z")
        self.assertTrue(report["replacement_probe"]["verified"])
        self.assertEqual(report["replacement_probe"]["replacement_ticker"], "CCC")
        self.assertEqual(report["candidate_replacement_evidence"], "COUNTERFACTUAL_REPLACEMENT_VERIFIED")
        self.assertEqual([r["ticker"] for r in select.call_args.args[0]], ["BBB", "CCC"])
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
