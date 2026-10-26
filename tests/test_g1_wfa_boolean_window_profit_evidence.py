"""G1 regression: boolean OOS window profits cannot certify WFA performance."""
import unittest

import numpy as np
import pandas as pd

from hanz_app.research.hanz_walk_forward_evidence_validator import validate


class G1BooleanWindowProfitEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.trades = pd.DataFrame({
            "window_id": ["W1"] * 15 + ["W2"] * 15,
            "trade_id": list(range(30)),
            "is_oos": [True] * 30,
            "r_multiple": [1.0] * 30,
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

    def test_boolean_window_profit_column_is_rejected(self):
        windows = self.windows.copy()
        windows["oos_profit_r"] = [True, True]
        with self.assertRaisesRegex(ValueError, "Invalid OOS window profit evidence"):
            validate(self.trades, windows, 95.0)

    def test_mixed_native_and_numpy_boolean_window_profit_is_rejected(self):
        for value in (True, False, np.bool_(True), np.bool_(False)):
            with self.subTest(value_type=type(value).__name__, value=bool(value)):
                windows = self.windows.copy()
                windows["oos_profit_r"] = pd.Series([value, 15.0], dtype=object)
                with self.assertRaisesRegex(ValueError, "Invalid OOS window profit evidence"):
                    validate(self.trades, windows, 95.0)

    def test_valid_numeric_and_numeric_string_window_profits_still_pass(self):
        self.assertTrue(validate(self.trades, self.windows, 95.0)["passed"])
        windows = self.windows.copy()
        windows["oos_profit_r"] = ["15.0", "15.0"]
        self.assertTrue(validate(self.trades, windows, 95.0)["passed"])


if __name__ == "__main__":
    unittest.main()
