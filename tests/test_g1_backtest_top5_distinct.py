"""G1 regression: five-year replay must select five DISTINCT latest ticker snapshots."""
import unittest
from unittest.mock import patch

from hanz_app.research.generate_top5_5y_backtest import _top5_symbols


def row(ticker, score, action="WAIT"):
    return {
        "ticker": ticker,
        "risk_validation": {
            "hanz_action": action,
            "canonical_rank_score": score,
        },
    }


class G1BacktestDistinctTop5Tests(unittest.TestCase):
    def test_duplicate_monitor_rows_cannot_consume_multiple_top5_slots(self):
        # The source query returns newest-first, including historical snapshots.
        snapshots = [row("AAA", 95), row("aaa", 99), row("BBB", 90),
                     row("CCC", 80), row("DDD", 70), row("EEE", 60)]
        with patch("hanz_app.research.generate_top5_5y_backtest._get_monitor_rows",
                   return_value=snapshots):
            self.assertEqual(_top5_symbols(), ["AAA", "BBB", "CCC", "DDD", "EEE"])

    def test_newer_exclusion_cannot_be_bypassed_by_older_eligible_row(self):
        snapshots = [row("AAA", 99, "AVOID"), row("AAA", 98),
                     row("BBB", 90), row("CCC", 80), row("DDD", 70),
                     row("EEE", 60)]
        with patch("hanz_app.research.generate_top5_5y_backtest._get_monitor_rows",
                   return_value=snapshots):
            self.assertEqual(_top5_symbols(), ["BBB", "CCC", "DDD", "EEE"])

    def test_empty_ticker_cannot_be_selected_as_backtest_evidence(self):
        snapshots = [row(None, 100), row("  ", 100), row("BBB", 90)]
        with patch("hanz_app.research.generate_top5_5y_backtest._get_monitor_rows",
                   return_value=snapshots):
            self.assertEqual(_top5_symbols(), ["BBB"])

    def test_normalized_duplicate_tickers_preserve_newest_rank(self):
        snapshots = [row(" bbb ", 10), row("BBB", 100),
                     row("AAA", 90)]
        with patch("hanz_app.research.generate_top5_5y_backtest._get_monitor_rows",
                   return_value=snapshots):
            self.assertEqual(_top5_symbols(), ["AAA", "BBB"])


if __name__ == "__main__":
    unittest.main()
