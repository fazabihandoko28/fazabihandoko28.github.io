"""G1 regression: entry-only OOS exports cannot hide IS-origin trades."""
import unittest
import pandas as pd
from hanz_app.research.hanz_walk_forward_evidence_validator import validate


class G1EntryOnlyOOSBoundsTests(unittest.TestCase):
    def setUp(self):
        self.trades = pd.DataFrame({
            "window_id": ["W1"] * 15 + ["W2"] * 15,
            "trade_id": list(range(30)),
            "is_oos": [True] * 30,
            "r_multiple": [1.0] * 30,
            "entry_date": ["2019-12-31"] * 15 + ["2024-01-01"] * 15,
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

    def test_is_origin_entry_only_export_is_rejected(self):
        # Before fix, absence of exit_date/trade_date skipped all OOS date checks.
        with self.assertRaisesRegex(ValueError, "OOS trade outside assigned"):
            validate(self.trades, self.windows, 95.0)

    def test_valid_entry_only_export_still_passes(self):
        self.trades.loc[:14, "entry_date"] = "2021-01-01"
        report = validate(self.trades, self.windows, 95.0)
        self.assertTrue(report["passed"])

    def test_undated_legacy_export_still_supported(self):
        report = validate(self.trades.drop(columns=["entry_date"]), self.windows, 95.0)
        self.assertTrue(report["passed"])


if __name__ == "__main__":
    unittest.main()
