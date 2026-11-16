"""G2 integration tests: actual monitor schema, fail-closed selection."""
import unittest
from unittest.mock import patch

from hanz_app.research.g2_monitor_adapter import select_monitor_top_five
from hanz_app.research.g2_production_top5 import build_report


def monitor(ticker, timestamp, eligible=True, score=20):
    return {"ticker": ticker, "updated_at": timestamp,
            "risk_validation": {"canonical_rank_score": score},
            "_test_eligible": eligible}


class G2MonitorIntegrationTests(unittest.TestCase):
    @patch("hanz_app.research.generate_top5_5y_backtest._rank",
           side_effect=lambda r: r["risk_validation"]["canonical_rank_score"])
    @patch("hanz_app.research.generate_top5_5y_backtest._eligible",
           side_effect=lambda r: r["_test_eligible"])
    def test_real_schema_replacement_and_no_buy(self, _eligible, _rank):
        rows = [monitor("AAA", "2026-11-13T18:00:00+00:00"),
                monitor("BBB", "2026-11-13T18:00:00+00:00", False),
                monitor("CCC", "2026-11-13T18:00:00+00:00"),
                monitor("DDD", "2026-11-13T18:00:00+00:00"),
                monitor("EEE", "2026-11-13T18:00:00+00:00"),
                monitor("FFF", "2026-11-13T18:00:00+00:00")]
        result = build_report(rows, as_of="2026-11-16",
                              generated_at="2026-11-16T00:00:00+00:00")
        self.assertEqual(result["selected"], ["AAA", "CCC", "DDD", "EEE", "FFF"])
        self.assertFalse(result["buy_authorized"])
        self.assertFalse(result["live_verified"])
        self.assertFalse(result["oos_certified"])

    @patch("hanz_app.research.generate_top5_5y_backtest._rank", return_value=99)
    @patch("hanz_app.research.generate_top5_5y_backtest._eligible",
           side_effect=lambda r: r["_test_eligible"])
    def test_newer_exclusion_wins_same_day(self, _eligible, _rank):
        rows = [monitor("AAA", "2026-11-13T12:00:00Z", True),
                monitor("AAA", "2026-11-13T18:00:00Z", False),
                monitor("BBB", "2026-11-13T18:00:00Z", True)]
        result = select_monitor_top_five(rows, as_of="2026-11-16")
        self.assertEqual(result["selected"], ["BBB"])

    @patch("hanz_app.research.generate_top5_5y_backtest._rank", return_value=99)
    @patch("hanz_app.research.generate_top5_5y_backtest._eligible", return_value=True)
    def test_missing_or_naive_timestamp_excluded(self, _eligible, _rank):
        rows = [monitor("AAA", "2026-11-13T18:00:00"),
                monitor("BBB", "invalid")]
        self.assertEqual(select_monitor_top_five(rows, as_of="2026-11-16")["selected"], [])

    @patch("hanz_app.research.generate_top5_5y_backtest._rank", return_value=99)
    @patch("hanz_app.research.generate_top5_5y_backtest._eligible",
           side_effect=lambda r: r["_test_eligible"])
    def test_future_same_day_snapshot_excluded(self, _eligible, _rank):
        rows = [monitor("AAA", "2026-11-16T15:00:00Z"),
                monitor("BBB", "2026-11-16T14:00:00Z")]
        result = select_monitor_top_five(rows, as_of="2026-11-16T14:30:00Z")
        self.assertEqual(result["selected"], ["BBB"])
        self.assertFalse(result["buy_authorized"])

    @patch("hanz_app.research.generate_top5_5y_backtest._rank", return_value=99)
    @patch("hanz_app.research.generate_top5_5y_backtest._eligible",
           side_effect=lambda r: r["_test_eligible"])
    def test_future_exclusion_cannot_override_prior_eligible(self, _eligible, _rank):
        rows = [monitor("AAA", "2026-11-16T14:00:00Z", True),
                monitor("AAA", "2026-11-16T15:00:00Z", False)]
        result = select_monitor_top_five(rows, as_of="2026-11-16T14:30:00Z")
        self.assertEqual(result["selected"], ["AAA"])

    def test_naive_intraday_cutoff_rejected(self):
        with self.assertRaises(ValueError):
            select_monitor_top_five([], as_of="2026-11-16T14:30:00")


if __name__ == "__main__":
    unittest.main()
