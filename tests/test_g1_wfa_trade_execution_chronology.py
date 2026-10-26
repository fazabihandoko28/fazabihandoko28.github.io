"""G1 regression: trade execution date must respect entry/exit chronology."""
import unittest

import pandas as pd

from hanz_app.research.hanz_walk_forward_evidence_validator import validate


class G1TradeExecutionChronologyTests(unittest.TestCase):
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

    def test_trade_before_entry_rejected_even_inside_oos_window(self):
        self.trades.loc[0, "trade_date"] = "2020-12-31"
        with self.assertRaisesRegex(ValueError, "trade before entry"):
            validate(self.trades, self.windows, 95.0)

    def test_trade_after_exit_rejected_even_inside_oos_window(self):
        self.trades.loc[0, "trade_date"] = "2021-01-03"
        with self.assertRaisesRegex(ValueError, "trade after exit"):
            validate(self.trades, self.windows, 95.0)

    def test_consistent_trade_chronology_still_passes(self):
        self.assertTrue(validate(self.trades, self.windows, 95.0)["passed"])

    def test_partial_legacy_date_exports_stay_supported(self):
        self.assertTrue(validate(self.trades.drop(columns=["entry_date", "exit_date"]),
                                 self.windows, 95.0)["passed"])
        self.trades.loc[0, "trade_date"] = "2020-12-31"
        with self.assertRaisesRegex(ValueError, "trade before entry"):
            validate(self.trades.drop(columns=["exit_date"]), self.windows, 95.0)
        self.trades.loc[0, "trade_date"] = "2021-01-03"
        with self.assertRaisesRegex(ValueError, "trade after exit"):
            validate(self.trades.drop(columns=["entry_date"]), self.windows, 95.0)


if __name__ == "__main__":
    unittest.main()
