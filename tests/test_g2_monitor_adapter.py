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

    @patch("hanz_app.research.generate_top5_5y_backtest._rank",
           side_effect=lambda r: r["risk_validation"]["canonical_rank_score"])
    @patch("hanz_app.research.generate_top5_5y_backtest._eligible",
           side_effect=lambda r: r["_test_eligible"])
    def test_conflicting_equal_timestamp_fails_closed_in_both_orders(self, _eligible, _rank):
        approved = monitor("AAA", "2026-11-16T10:00:00Z", True, 90)
        rejected = monitor("AAA", "2026-11-16T10:00:00Z", False, 90)
        for rows in ([approved, rejected], [rejected, approved]):
            result = select_monitor_top_five(rows, as_of="2026-11-16T11:00:00Z")
            self.assertNotIn("AAA", result["selected"])
            self.assertFalse(result["buy_authorized"])

    @patch("hanz_app.research.generate_top5_5y_backtest._rank",
           side_effect=lambda r: r["risk_validation"]["canonical_rank_score"])
    @patch("hanz_app.research.generate_top5_5y_backtest._eligible",
           side_effect=lambda r: r["_test_eligible"])
    def test_identical_duplicate_snapshot_keeps_candidate(self, _eligible, _rank):
        approved = monitor("AAA", "2026-11-16T10:00:00Z", True, 90)
        result = select_monitor_top_five([approved, approved],
                                         as_of="2026-11-16T11:00:00Z")
        self.assertEqual(result["selected"], ["AAA"])

    def test_missing_action_with_positive_score_is_not_eligible(self):
        from hanz_app.research.generate_top5_5y_backtest import _eligible
        row = {"ticker": "AAA", "risk_validation": {
            "canonical_rank_score": 90,
            "top5_excluded": False,
            "momentum_guard": {"blocked": False},
            "volatility_status": "NORMAL",
            "zero_volume_days20": 0,
            "avg_value20": 500000000,
        }}
        self.assertFalse(_eligible(row))
        self.assertFalse(_eligible({**row, "hanz_action": ""}))

    def test_malformed_risk_validation_fails_closed_without_crash(self):
        from hanz_app.research.generate_top5_5y_backtest import _eligible, _rank
        for bad in ([], [1], "bad", 17, True):
            row = {"ticker": "AAA", "updated_at": "2026-11-17T10:00:00Z",
                   "risk_validation": bad}
            self.assertFalse(_eligible(row))
            self.assertEqual(_rank(row), 0)
            self.assertEqual(select_monitor_top_five([row], as_of="2026-11-17")["selected"], [])

    def test_naive_intraday_cutoff_rejected(self):
        with self.assertRaises(ValueError):
            select_monitor_top_five([], as_of="2026-11-16T14:30:00")


    @patch("hanz_app.research.generate_top5_5y_backtest._rank",
           side_effect=lambda r: r["risk_validation"].get("canonical_rank_score", 0))
    @patch("hanz_app.research.generate_top5_5y_backtest._eligible",
           side_effect=lambda r: not r["risk_validation"].get("top5_excluded", False))
    def test_malformed_newest_snapshot_never_falls_back(self, _eligible, _rank):
        older = monitor("AAA", "2026-11-16T09:00:00Z", True, 90)
        malformed = {**monitor("AAA", "2026-11-16T10:00:00Z"), "risk_validation": []}
        valid = monitor("BBB", "2026-11-16T10:00:00Z", True, 70)
        for rows in ([older, malformed, valid], [valid, malformed, older]):
            result = select_monitor_top_five(rows, as_of="2026-11-16")
            self.assertEqual(result["selected"], ["BBB"])
            self.assertFalse(result["buy_authorized"])

    @patch("hanz_app.research.generate_top5_5y_backtest._rank",
           side_effect=lambda r: r["risk_validation"].get("canonical_rank_score", 0))
    @patch("hanz_app.research.generate_top5_5y_backtest._eligible",
           side_effect=lambda r: not r["risk_validation"].get("top5_excluded", False))
    def test_equal_timestamp_malformed_conflict_fails_closed(self, _eligible, _rank):
        valid = monitor("AAA", "2026-11-16T10:00:00Z", True, 90)
        malformed = {**valid, "risk_validation": []}
        for rows in ([valid, malformed], [malformed, valid]):
            self.assertEqual(
                select_monitor_top_five(rows, as_of="2026-11-16")["selected"], [])

    @patch("hanz_app.research.generate_top5_5y_backtest._rank",
           side_effect=lambda r: r["risk_validation"].get("canonical_rank_score", 0))
    @patch("hanz_app.research.generate_top5_5y_backtest._eligible",
           side_effect=lambda r: not r["risk_validation"].get("top5_excluded", False))
    def test_future_malformed_snapshot_does_not_override(self, _eligible, _rank):
        valid = monitor("AAA", "2026-11-16T09:00:00Z", True, 90)
        malformed = {**valid, "updated_at": "2026-11-16T12:00:00Z",
                     "risk_validation": []}
        result = select_monitor_top_five(
            [valid, malformed], as_of="2026-11-16T10:00:00Z")
        self.assertEqual(result["selected"], ["AAA"])


if __name__ == "__main__":
    unittest.main()
