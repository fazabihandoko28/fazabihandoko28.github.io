"""Regression for production five-year backtest report semantics."""
import unittest
from pathlib import Path


class BacktestReportingTests(unittest.TestCase):
    def test_report_never_mislabels_replay_as_oos(self):
        source = Path("src/hanz_app/research/generate_top5_5y_backtest.py").read_text()
        self.assertIn('"actual_point_in_time_oos_verified": False', source)
        self.assertIn('"reconstructed_point_in_time_oos_verified": False', source)
        self.assertIn('"net_after_costs_verified": False', source)
        self.assertIn('"buy_authorized": False', source)

    def test_shortfall_diagnostics_distinguish_eligibility_from_price_history(self):
        source = Path("src/hanz_app/research/generate_top5_5y_backtest.py").read_text()
        self.assertIn('"eligible_production_shortfall"', source)
        self.assertIn('INSUFFICIENT_ELIGIBLE_PRODUCTION_CANDIDATES', source)
        self.assertIn('INSUFFICIENT_VALID_FIVE_YEAR_PRICE_HISTORY', source)


if __name__ == "__main__":
    unittest.main()
