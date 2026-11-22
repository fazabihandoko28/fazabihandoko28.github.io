"""Fail-closed production Top 5 report regression."""
import unittest
from unittest.mock import patch
from hanz_app.research.g2_production_top5 import build_report


class ProductionTopFiveReportTests(unittest.TestCase):
    @patch("hanz_app.research.g2_production_top5.select_monitor_top_five")
    def test_shortfall_is_explicit_and_never_certified(self, select):
        select.return_value = {
            "selected": ["BJTM", "EXCL", "TBIG"],
            "vacant_slots": 2,
            "selection_complete": False,
            "research_only": True,
            "buy_authorized": False,
            "oos_certified": False,
        }
        rows = [{"ticker": "BJTM"}, {"ticker": "EXCL"}, {"ticker": "TBIG"}]
        report = build_report(rows, as_of="2026-11-20T23:00:00+00:00",
                              generated_at="2026-11-20T23:00:00+00:00")
        self.assertEqual(report["candidate_shortfall"], 2)
        self.assertEqual(report["eligible_selected_count"], 3)
        self.assertEqual(report["production_unique_tickers"], 3)
        self.assertEqual(report["candidate_shortfall_reason"],
                         "INSUFFICIENT_ELIGIBLE_PRODUCTION_SIGNALS")
        self.assertFalse(report["historical_point_in_time_oos_verified"])
        self.assertFalse(report["backtest_5y_certified"])
        self.assertFalse(report["buy_authorized"])

    @patch("hanz_app.research.g2_production_top5.select_monitor_top_five")
    def test_full_selection_still_not_oos_certified(self, select):
        select.return_value = {
            "selected": ["A", "B", "C", "D", "E"],
            "vacant_slots": 0,
            "selection_complete": True,
            "research_only": True,
            "buy_authorized": False,
            "oos_certified": False,
        }
        report = build_report([{"ticker": s} for s in "ABCDE"],
                              as_of="2026-11-20T23:00:00+00:00",
                              generated_at="2026-11-20T23:00:00+00:00")
        self.assertEqual(report["candidate_shortfall"], 0)
        self.assertIsNone(report["candidate_shortfall_reason"])
        self.assertFalse(report["historical_point_in_time_oos_verified"])
        self.assertFalse(report["buy_authorized"])


    @patch("hanz_app.research.g2_production_top5.select_monitor_top_five")
    def test_relaxed_research_respects_cutoff_and_newest_snapshot(self, select):
        select.return_value = {
            "selected": [], "vacant_slots": 5, "selection_complete": False,
            "research_only": True, "buy_authorized": False, "oos_certified": False,
        }
        def snapshot(ticker, when, value=60000000):
            return {"ticker": ticker, "updated_at": when, "risk_validation": {
                "hanz_action": "AVOID", "avg_value20": value,
                "zero_volume_days20": 1, "volatility_status": "NORMAL",
            }}
        rows = [
            snapshot("FUTURE", "2026-11-21T00:00:00Z"),
            snapshot("STALE", "2026-11-19T00:00:00Z"),
            snapshot("STALE", "2026-11-20T12:00:00Z", value=1000000),
            snapshot("VALID", "2026-11-20T11:00:00Z"),
        ]
        report = build_report(rows, as_of="2026-11-20T23:00:00Z",
                              generated_at="2026-11-20T23:00:00Z")
        self.assertEqual(report["relaxed_research_top5"], ["VALID"])
        self.assertFalse(report["relaxed_research_buy_authorized"])
        self.assertFalse(report["buy_authorized"])


if __name__ == "__main__":
    unittest.main()
