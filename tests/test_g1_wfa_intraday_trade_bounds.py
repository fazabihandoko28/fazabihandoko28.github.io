"""G1: OOS trade provenance must retain intraday timestamp precision."""
import unittest

import pandas as pd

from hanz_app.research.hanz_walk_forward_evidence_validator import validate


class G1IntradayTradeBoundsTests(unittest.TestCase):
    def setUp(self):
        self.windows = pd.DataFrame({
            "window_id": ["W1", "W2"],
            "oos_profit_r": [15.0, 15.0],
            "is_profit_r": [15.0, 15.0],
            "is_years": [1.0, 1.0],
            "oos_years": [1.0, 1.0],
            "oos_start": ["2020-01-01T09:00:00Z", "2023-01-01T09:00:00Z"],
            "oos_end": ["2022-12-31T15:00:00Z", "2025-12-31T15:00:00Z"],
        })
        self.trades = pd.DataFrame({
            "window_id": ["W1"] * 15 + ["W2"] * 15,
            "trade_id": list(range(30)),
            "is_oos": [True] * 30,
            "r_multiple": [1.0] * 30,
            "trade_date": ["2020-01-01T10:00:00Z"] * 15
                          + ["2023-01-01T10:00:00Z"] * 15,
        })

    def test_assigned_outside_intraday_bounds_rejected(self):
        for stamp in ("2020-01-01T08:59:59Z", "2022-12-31T15:00:01Z"):
            with self.subTest(stamp=stamp):
                trades = self.trades.copy()
                trades.loc[0, "trade_date"] = stamp
                with self.assertRaisesRegex(ValueError, "OOS trade outside assigned"):
                    validate(trades, self.windows, 95.0)

    def test_unassigned_outside_intraday_bounds_rejected(self):
        for stamp in ("2020-01-01T08:59:59Z", "2022-12-31T15:00:01Z"):
            with self.subTest(stamp=stamp):
                trades = self.trades.drop(columns=["window_id"]).copy()
                trades.loc[0, "trade_date"] = stamp
                with self.assertRaisesRegex(ValueError, "Unassigned OOS trade outside all"):
                    validate(trades, self.windows, 95.0)

    def test_assigned_exact_boundaries_accepted(self):
        for stamp in ("2020-01-01T09:00:00Z", "2022-12-31T15:00:00Z"):
            with self.subTest(stamp=stamp):
                trades = self.trades.copy()
                trades.loc[0, "trade_date"] = stamp
                self.assertTrue(validate(trades, self.windows, 95.0)["passed"])

    def test_unassigned_exact_boundaries_accepted(self):
        for stamp in ("2020-01-01T09:00:00Z", "2022-12-31T15:00:00Z"):
            with self.subTest(stamp=stamp):
                trades = self.trades.drop(columns=["window_id"]).copy()
                trades.loc[0, "trade_date"] = stamp
                self.assertTrue(validate(trades, self.windows, 95.0)["passed"])


    def test_legacy_date_only_end_includes_intraday_exit(self):
        # Existing G1 exports use date-only end dates to mean the whole day.
        # Tightening intraday provenance must not invalidate those exports.
        windows = self.windows.copy()
        windows.loc[0, "oos_end"] = "2022-12-31"
        for assigned in (True, False):
            with self.subTest(assigned=assigned):
                trades = self.trades.copy()
                trades.loc[0, "trade_date"] = "2022-12-31T15:00:01Z"
                if not assigned:
                    trades = trades.drop(columns=["window_id"])
                self.assertTrue(validate(trades, windows, 95.0)["passed"])



if __name__ == "__main__":
    unittest.main()
