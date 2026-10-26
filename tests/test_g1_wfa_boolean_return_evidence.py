"""G1: boolean OOS returns must never masquerade as numeric realized R."""
import unittest

import numpy as np
import pandas as pd

from hanz_app.research.hanz_walk_forward_evidence_validator import validate


class G1BooleanReturnEvidenceTests(unittest.TestCase):
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

    def test_all_boolean_returns_are_rejected(self):
        self.trades["r_multiple"] = [True] * 30
        with self.assertRaisesRegex(ValueError, "Invalid OOS trade return evidence"):
            validate(self.trades, self.windows, 95.0)

    def test_mixed_native_and_numpy_boolean_returns_are_rejected(self):
        for value in (True, np.bool_(True)):
            with self.subTest(value_type=type(value).__name__):
                trades = self.trades.copy()
                trades["r_multiple"] = pd.Series(
                    [value] + [1.0] * 29, dtype=object
                )
                with self.assertRaisesRegex(ValueError, "Invalid OOS trade return evidence"):
                    validate(trades, self.windows, 95.0)

    def test_valid_numeric_returns_still_pass(self):
        self.assertTrue(validate(self.trades, self.windows, 95.0)["passed"])
        trades = self.trades.copy()
        trades["r_multiple"] = ["1.0"] * 30
        self.assertTrue(validate(trades, self.windows, 95.0)["passed"])


if __name__ == "__main__":
    unittest.main()
