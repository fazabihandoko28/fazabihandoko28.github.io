"""G1 regression: boolean annualization evidence cannot certify WFE."""
import unittest

import numpy as np
import pandas as pd

from hanz_app.research.hanz_walk_forward_evidence_validator import validate


class G1BooleanAnnualizationEvidenceTests(unittest.TestCase):
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

    def test_boolean_profit_and_years_are_rejected(self):
        for col in ("is_profit_r", "is_years", "oos_years"):
            for value in (True, False, np.bool_(True), np.bool_(False)):
                with self.subTest(column=col, value=bool(value), kind=type(value).__name__):
                    windows = self.windows.copy()
                    windows[col] = pd.Series([value, 1.0], dtype=object)
                    with self.assertRaisesRegex(ValueError, "Invalid walk-forward annualization evidence"):
                        validate(self.trades, windows, 95.0)

    def test_valid_numeric_annualization_still_passes(self):
        report = validate(self.trades, self.windows, 95.0)
        self.assertTrue(report["passed"])
        self.assertAlmostEqual(report["wfe"], 1.0)

    def test_valid_numeric_string_annualization_still_passes(self):
        windows = self.windows.copy()
        for col in ("is_profit_r", "is_years", "oos_years"):
            windows[col] = windows[col].astype(str)
        report = validate(self.trades, windows, 95.0)
        self.assertTrue(report["passed"])
        self.assertAlmostEqual(report["wfe"], 1.0)


if __name__ == "__main__":
    unittest.main()
