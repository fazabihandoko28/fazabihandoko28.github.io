"""G1 regression: all supplied trade timestamps must fit assigned OOS windows."""
import unittest

import pandas as pd

from hanz_app.research.hanz_walk_forward_evidence_validator import validate


class G1AllTradeDatesOOSBoundsTests(unittest.TestCase):
    def setUp(self):
        self.trades = pd.DataFrame({
            "window_id": ["W1"] * 15 + ["W2"] * 15,
            "trade_id": list(range(30)),
            "is_oos": [True] * 30,
            "r_multiple": [1.0] * 30,
            "entry_date": ["2021-01-01"] * 15 + ["2024-01-01"] * 15,
            "exit_date": ["2021-01-02"] * 15 + ["2024-01-02"] * 15,
            "trade_date": ["2021-01-01"] * 15 + ["2024-01-01"] * 15,
        })
        self.windows = pd.DataFrame({
            "window_id": ["W1", "W2"],
            "oos_profit_r": [15.0, 15.0],
            "is_profit_r": [15.0, 15.0],
            "is_years": [1.0, 1.0],
            "oos_years": [1.0, 1.0],
            "oos_start": ["2020-01-01", "2023-01-01"],
            "oos_end": ["2022-12-31", "2025-12-31"],
        })

    def test_out_of_window_trade_date_is_rejected_even_with_exit_date(self):
        # Old logic skipped trade_date whenever exit_date existed.
        self.trades.loc[0, "trade_date"] = "2019-12-31"
        with self.assertRaisesRegex(ValueError, "OOS trade outside assigned"):
            validate(self.trades, self.windows, 95.0)

    def test_consistent_three_date_export_passes(self):
        self.assertTrue(validate(self.trades, self.windows, 95.0)["passed"])

    def test_trade_date_only_export_still_passes(self):
        only_trade_date = self.trades.drop(columns=["entry_date", "exit_date"])
        self.assertTrue(validate(only_trade_date, self.windows, 95.0)["passed"])


if __name__ == "__main__":
    unittest.main()
