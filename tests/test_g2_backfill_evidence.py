"""G2 research-only backfill: verify actual replacement and no false coverage."""
import unittest
from unittest.mock import patch

from hanz_app.research.generate_top5_5y_backtest import (
    _backfill_five_year_research, _selection_coverage,
)


class G2BackfillEvidenceTests(unittest.TestCase):
    @patch("hanz_app.research.generate_top5_5y_backtest._summary")
    @patch("hanz_app.research.generate_top5_5y_backtest._five_year_replay_series",
           side_effect=lambda series: series)
    @patch("hanz_app.research.generate_top5_5y_backtest.YahooFinanceProvider")
    def test_short_history_candidate_replaced_without_false_pass(
            self, provider, _replay, summary):
        candidates = ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF"]
        available = {s: type("Mapping", (), {"symbol": s})()
                     for s in candidates}
        provider.return_value.load_series.side_effect = (
            lambda market, symbol: symbol)
        summary.side_effect = lambda symbol, series, report: {
            "status": "LIMITED_HISTORY" if symbol == "CCC" else "OK",
            "history_gap_reason": "SHORT_CALENDAR_SPAN" if symbol == "CCC" else None,
        }
        validator = type("Validator", (), {"validate": lambda self, series: object()})()
        selected, results, skipped = _backfill_five_year_research(
            candidates, available, validator)
        self.assertEqual(selected, ["AAA", "BBB", "DDD", "EEE", "FFF"])
        self.assertEqual(skipped["CCC"], "SHORT_CALENDAR_SPAN")
        coverage = _selection_coverage(selected, available, results, {})
        self.assertTrue(coverage["backtest_complete"])

    def test_incomplete_history_never_certifies_five(self):
        symbols = ["AAA", "BBB", "CCC", "DDD", "EEE"]
        available = {s: object() for s in symbols}
        results = {s: {"status": "OK"} for s in symbols[:4]}
        results["EEE"] = {"status": "LIMITED_HISTORY"}
        coverage = _selection_coverage(symbols, available, results, {})
        self.assertEqual(coverage["five_year_history_count"], 4)
        self.assertFalse(coverage["backtest_complete"])


if __name__ == "__main__":
    unittest.main()
