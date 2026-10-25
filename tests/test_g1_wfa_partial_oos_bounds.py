"""G1 regression: incomplete OOS date exports cannot manufacture five years."""
import unittest

import pandas as pd

from hanz_app.research.hanz_walk_forward_evidence_validator import validate


class G1PartialOOSBoundsTests(unittest.TestCase):
    def setUp(self):
        # Otherwise healthy strategy: only chronology provenance is defective.
        self.trades = pd.DataFrame({
            "trade_id": list(range(30)),
            "is_oos": [True] * 30,
            "r_multiple": [1.0] * 30,
        })
        self.windows = pd.DataFrame({
            "window_id": ["W1", "W2"],
            "oos_profit_r": [15.0, 15.0],
            "is_profit_r": [15.0, 15.0],
            "is_years": [0.5, 0.5],
            "oos_years": [0.5, 0.5],
            "window_start": ["2020-01-01", "2023-01-01"],
            "window_end": ["2026-01-01", "2026-01-01"],
            "oos_start": ["2025-01-01", "2025-07-01"],
        })

    def test_missing_oos_end_cannot_pass_five_year_history(self):
        # Before fix: window_start (2020) and window_end (2026) gave 6Y
        # even though the exported OOS start dates begin in 2025.
        with self.assertRaisesRegex(ValueError, "Incomplete walk-forward OOS chronology"):
            validate(self.trades, self.windows, 95.0)

    def test_missing_oos_start_cannot_pass_five_year_history(self):
        incomplete = self.windows.drop(columns=["oos_start"]).assign(
            oos_end=["2025-06-30", "2026-01-01"]
        )
        with self.assertRaisesRegex(ValueError, "Incomplete walk-forward OOS chronology"):
            validate(self.trades, incomplete, 95.0)

    def test_complete_oos_bounds_keep_five_year_gate_strict(self):
        complete = self.windows.assign(oos_end=["2025-06-30", "2026-01-01"])
        result = validate(self.trades, complete, 95.0)
        self.assertFalse(result["checks"]["five_year_history"])
        self.assertFalse(result["passed"])
        self.assertLess(result["backtest_years"], 5.0)

    def test_legacy_exports_without_either_oos_bound_remain_supported(self):
        legacy = self.windows.drop(columns=["oos_start"])
        result = validate(self.trades, legacy, 95.0)
        self.assertTrue(result["checks"]["five_year_history"])


if __name__ == "__main__":
    unittest.main()
