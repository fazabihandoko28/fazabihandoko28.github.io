"""G1: assigned OOS trades must reconcile to reported window R."""
import unittest
import pandas as pd
from hanz_app.research.hanz_walk_forward_evidence_validator import validate


class G1WindowProfitReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.trades = pd.DataFrame({
            "window_id": ["W1"] * 24 + ["W2"] * 2 + ["W3"] * 2 + ["W4"] * 2,
            "trade_id": list(range(30)),
            "is_oos": [True] * 30,
            "r_multiple": [1.0] * 24 + [-1.0] * 6,
        })
        self.windows = pd.DataFrame({
            "window_id": ["W1", "W2", "W3", "W4"],
            "oos_profit_r": [6.0] * 4,
            "is_profit_r": [6.0] * 4,
            "is_years": [1.0] * 4,
            "oos_years": [1.0] * 4,
            "oos_start": ["2020-01-01", "2021-07-01", "2023-01-02", "2024-07-02"],
            "oos_end": ["2021-06-30", "2023-01-01", "2024-07-01", "2026-01-01"],
        })

    def test_fabricated_profitable_windows_rejected(self):
        with self.assertRaisesRegex(ValueError, "Contradictory walk-forward window profit evidence"):
            validate(self.trades, self.windows, 95.0)

    def test_corrected_window_totals_do_not_raise(self):
        windows = self.windows.copy()
        windows["oos_profit_r"] = [24.0, -2.0, -2.0, -2.0]
        result = validate(self.trades, windows, 95.0)
        self.assertFalse(result["checks"]["profitable_window_consistency"])

    def test_valid_positive_window_totals_pass(self):
        trades = self.trades.copy()
        trades["r_multiple"] = [1.0] * 30
        windows = self.windows.copy()
        windows["oos_profit_r"] = [24.0, 2.0, 2.0, 2.0]
        result = validate(trades, windows, 95.0)
        self.assertTrue(result["passed"])

    def test_valid_numeric_string_totals_pass(self):
        trades = self.trades.copy()
        trades["r_multiple"] = [1.0] * 30
        windows = self.windows.copy()
        windows["oos_profit_r"] = ["24.0", "2.0", "2.0", "2.0"]
        result = validate(trades, windows, 95.0)
        self.assertTrue(result["passed"])


    def _empty_window_fixture(self):
        trades = pd.DataFrame({
            "window_id": ["W1"] * 10 + ["W2"] * 10 + ["W3"] * 10,
            "trade_id": list(range(30)),
            "is_oos": [True] * 30,
            "r_multiple": [1.0] * 30,
        })
        windows = pd.DataFrame({
            "window_id": ["W1", "W2", "W3", "W4"],
            "oos_profit_r": [10.0, 10.0, 10.0, 5.0],
            "is_profit_r": [10.0, 10.0, 10.0, 5.0],
            "is_years": [1.0] * 4,
            "oos_years": [1.0] * 4,
            "oos_start": ["2020-01-01", "2021-07-01", "2023-01-02", "2024-07-02"],
            "oos_end": ["2021-06-30", "2023-01-01", "2024-07-01", "2026-01-01"],
        })
        return trades, windows

    def test_empty_window_cannot_claim_fabricated_positive_r(self):
        trades, windows = self._empty_window_fixture()
        with self.assertRaisesRegex(ValueError, "Contradictory walk-forward window profit evidence"):
            validate(trades, windows, 95.0)

    def test_missing_window_cannot_disable_other_window_reconciliation(self):
        trades, windows = self._empty_window_fixture()
        windows.loc[3, "oos_profit_r"] = 0.0
        windows.loc[0, "oos_profit_r"] = 9.0
        with self.assertRaisesRegex(ValueError, "Contradictory walk-forward window profit evidence"):
            validate(trades, windows, 95.0)

    def test_zero_trade_window_with_zero_reported_r_is_valid(self):
        trades, windows = self._empty_window_fixture()
        windows.loc[3, "oos_profit_r"] = 0.0
        result = validate(trades, windows, 95.0)
        self.assertTrue(result["passed"])
        self.assertEqual(result["profitable_wf_pct"], 75.0)



if __name__ == "__main__":
    unittest.main()
