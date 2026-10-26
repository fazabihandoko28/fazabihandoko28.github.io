"""G1: unassigned dated OOS trades must belong to one common OOS window."""
import unittest

import pandas as pd

from hanz_app.research.hanz_walk_forward_evidence_validator import validate


class G1UnassignedSingleWindowTests(unittest.TestCase):
    def setUp(self):
        self.trades = pd.DataFrame({
            "trade_id": list(range(30)),
            "is_oos": [True] * 30,
            "r_multiple": [1.0] * 30,
            "entry_date": ["2021-01-01"] * 15 + ["2024-01-01"] * 15,
            "exit_date": ["2021-01-02"] * 15 + ["2024-01-02"] * 15,
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

    def test_cross_window_entry_exit_rejected(self):
        # Old validator checked both dates independently and falsely PASSED.
        self.trades.loc[0, "exit_date"] = "2024-01-02"
        with self.assertRaisesRegex(ValueError, "Unassigned OOS trade outside all"):
            validate(self.trades, self.windows, 95.0)

    def test_cross_window_execution_date_rejected(self):
        # Execution remains between entry and exit, but crosses test windows.
        self.trades.loc[0, "exit_date"] = "2024-01-02"
        self.trades["trade_date"] = self.trades["entry_date"]
        self.trades.loc[0, "trade_date"] = "2024-01-01"
        with self.assertRaisesRegex(ValueError, "Unassigned OOS trade outside all"):
            validate(self.trades, self.windows, 95.0)

    def test_valid_unassigned_trades_still_pass(self):
        self.assertTrue(validate(self.trades, self.windows, 95.0)["passed"])

    def test_is_only_trade_outside_oos_remains_excluded(self):
        outside = pd.DataFrame([{
            "trade_id": 30, "is_oos": False, "r_multiple": -1.0,
            "entry_date": "2019-01-01", "exit_date": "2019-01-02",
        }])
        trades = pd.concat([self.trades, outside], ignore_index=True)
        report = validate(trades, self.windows, 95.0)
        self.assertEqual(report["oos_trades"], 30)
        self.assertTrue(report["passed"])


if __name__ == "__main__":
    unittest.main()
