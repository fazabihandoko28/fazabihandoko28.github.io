"""Contract tests: replacement must be evidenced, never manufactured."""
import unittest
from unittest.mock import patch
from hanz_app.research.g2_production_top5 import build_report

STAMP = "2026-11-20T09:00:00+00:00"
CUTOFF = "2026-11-21T09:00:00+00:00"


def rows(count):
    return [
        {"ticker": f"T{i:03d}", "updated_at": STAMP,
         "risk_validation": {"rank_score": 100-i}}
        for i in range(count)
    ]


def fake_rank(row):
    return row["risk_validation"]["rank_score"]


class ReplacementEvidenceContract(unittest.TestCase):
    def report(self, count):
        with patch("hanz_app.research.generate_top5_5y_backtest._eligible",
                   side_effect=lambda row: True), patch(
                   "hanz_app.research.generate_top5_5y_backtest._rank",
                   side_effect=fake_rank):
            return build_report(rows(count), as_of=CUTOFF, generated_at=CUTOFF)

    def test_sixth_candidate_replaces_removed_leader(self):
        result = self.report(6)
        self.assertEqual(result["selected"], ["T000", "T001", "T002", "T003", "T004"])
        self.assertTrue(result["selection_complete"])
        self.assertEqual(result["replacement_probe"]["removed_ticker"], "T000")
        self.assertEqual(result["replacement_probe"]["replacement_ticker"], "T005")
        self.assertTrue(result["replacement_probe"]["verified"])
        self.assertFalse(result["historical_point_in_time_oos_verified"])
        self.assertEqual(result["status"], "RESEARCH_ONLY_NOT_CERTIFIED")

    def test_five_eligible_has_no_replacement(self):
        result = self.report(5)
        self.assertTrue(result["selection_complete"])
        self.assertFalse(result["replacement_probe"]["verified"])
        self.assertEqual(result["replacement_probe"]["reason"], "NO_ELIGIBLE_REPLACEMENT")

    def test_three_eligible_remain_unfilled(self):
        result = self.report(3)
        self.assertEqual(result["selected"], ["T000", "T001", "T002"])
        self.assertEqual(result["vacant_slots"], 2)
        self.assertFalse(result["replacement_probe"]["verified"])
        self.assertFalse(result["production_top5_complete"])
        self.assertFalse(result["historical_point_in_time_oos_verified"])


if __name__ == "__main__":
    unittest.main()
