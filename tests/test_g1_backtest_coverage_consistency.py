"""G1 backtest coverage must reject contradictory or double-counted ticker evidence."""
import unittest

from hanz_app.research.generate_top5_5y_backtest import _selection_coverage


class G1BacktestCoverageConsistencyTests(unittest.TestCase):
    def setUp(self):
        self.symbols = ["A", "B", "C", "D", "E"]
        self.available = dict.fromkeys(self.symbols)
        self.results = {symbol: {"status": "OK"} for symbol in self.symbols}

    def test_clean_complete_selection_still_passes(self):
        report = _selection_coverage(self.symbols, self.available, self.results, {})
        self.assertTrue(report["backtest_complete"])
        self.assertTrue(report["all_selected_accounted_for"])

    def test_same_ticker_result_and_error_never_certify_completion(self):
        report = _selection_coverage(
            self.symbols, self.available, self.results, {"A": "TIMEOUT"}
        )
        self.assertFalse(report["backtest_complete"])
        self.assertFalse(report["all_selected_accounted_for"])

    def test_double_count_does_not_hide_unaccounted_ticker(self):
        results = {key: value for key, value in self.results.items() if key != "E"}
        report = _selection_coverage(
            self.symbols, self.available, results, {"A": "TIMEOUT"}
        )
        self.assertFalse(report["all_selected_accounted_for"])
        self.assertFalse(report["backtest_complete"])

    def test_limited_history_remains_incomplete_but_accounted_for(self):
        results = {**self.results, "E": {"status": "LIMITED_HISTORY"}}
        report = _selection_coverage(self.symbols, self.available, results, {})
        self.assertEqual(report["five_year_history_count"], 4)
        self.assertTrue(report["all_selected_accounted_for"])
        self.assertFalse(report["backtest_complete"])

    def test_missing_mapping_is_accounted_for_but_incomplete(self):
        available = {key: value for key, value in self.available.items() if key != "E"}
        results = {key: value for key, value in self.results.items() if key != "E"}
        errors = {}
        report = _selection_coverage(self.symbols, available, results, errors)
        self.assertEqual(errors, {"E": "MISSING_UNIVERSE_MAPPING"})
        self.assertTrue(report["all_selected_accounted_for"])
        self.assertFalse(report["backtest_complete"])


if __name__ == "__main__":
    unittest.main()
