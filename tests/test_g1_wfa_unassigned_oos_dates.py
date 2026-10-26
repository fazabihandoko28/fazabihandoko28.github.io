"""G1 regression: dated OOS trades without window_id cannot come from outside OOS."""
import unittest

import pandas as pd

from hanz_app.research.hanz_walk_forward_evidence_validator import validate


class G1UnassignedOOSDateTests(unittest.TestCase):
    def setUp(self):
        self.trades = pd.DataFrame({
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

    def test_unassigned_trade_outside_every_oos_window_is_rejected(self):
        # Previously returned PASS: explicit OOS bounds were checked only
        # when trade rows also supplied window_id.
        self.trades.loc[0, "trade_date"] = "2019-01-01"
        with self.assertRaisesRegex(ValueError, "Unassigned OOS trade outside all"):
            validate(self.trades, self.windows, 95.0)

    def test_unassigned_trades_inside_oos_windows_remain_valid(self):
        self.assertTrue(validate(self.trades, self.windows, 95.0)["passed"])

    def test_is_only_trade_outside_oos_does_not_inflate_oos_sample(self):
        self.trades.loc[0, "is_oos"] = False
        self.trades.loc[0, "trade_date"] = "2019-01-01"
        result = validate(self.trades, self.windows, 95.0)
        self.assertEqual(result["oos_trades"], 29)
        self.assertFalse(result["passed"])
        self.assertFalse(result["checks"]["oos_trade_sample"])

    def test_undated_legacy_export_remains_supported(self):
        self.assertTrue(validate(self.trades.drop(columns=["trade_date"]),
                                 self.windows, 95.0)["passed"])


if __name__ == "__main__":
    unittest.main()
