"""G1 five-year OOS history must retain intraday anniversary precision."""
import unittest
import pandas as pd
from hanz_app.research.hanz_walk_forward_evidence_validator import (
    _evidence_span_years, validate,
)


class G1IntradayFiveYearSpanTests(unittest.TestCase):
    def _otherwise_healthy_evidence(self, final_end):
        windows = pd.DataFrame({
            "window_id": ["W1", "W2"],
            "oos_profit_r": [15.0, 15.0],
            "is_profit_r": [15.0, 15.0],
            "is_years": [1.0, 1.0],
            "oos_years": [1.0, 1.0],
            "oos_start": ["2020-01-01T23:59:00Z", "2023-01-01T00:00:00Z"],
            "oos_end": ["2022-12-31T23:59:00Z", final_end],
        })
        trades = pd.DataFrame({
            "trade_id": list(range(30)),
            "is_oos": [True] * 30,
            "r_multiple": [1.0] * 30,
            "trade_date": ["2020-01-02T00:00:00Z"] * 15
                          + ["2023-01-02T00:00:00Z"] * 15,
        })
        return trades, windows

    def test_same_date_but_earlier_time_does_not_complete_five_years(self):
        trades, windows = self._otherwise_healthy_evidence("2025-01-01T00:00:00Z")
        report = validate(trades, windows, 95.0)
        self.assertFalse(report["checks"]["five_year_history"])
        self.assertFalse(report["passed"])
        self.assertLess(report["backtest_years"], 5.0)
        self.assertTrue(all(value for name, value in report["checks"].items()
                            if name != "five_year_history"))

    def test_exact_fifth_anniversary_remains_valid(self):
        trades, windows = self._otherwise_healthy_evidence("2025-01-01T23:59:00Z")
        report = validate(trades, windows, 95.0)
        self.assertEqual(report["backtest_years"], 5.0)
        self.assertTrue(report["passed"])

    def test_legacy_date_only_anniversary_remains_valid(self):
        windows = pd.DataFrame({
            "oos_start": ["2020-01-01"],
            "oos_end": ["2025-01-01"],
        })
        self.assertEqual(_evidence_span_years(pd.DataFrame(), windows), 5.0)

    def test_leap_day_anniversary_uses_full_timestamp(self):
        windows = pd.DataFrame({
            "oos_start": ["2020-02-29T12:00:00Z"],
            "oos_end": ["2025-02-28T11:59:59Z"],
        })
        self.assertLess(_evidence_span_years(pd.DataFrame(), windows), 5.0)
        windows.loc[0, "oos_end"] = "2025-02-28T12:00:00Z"
        self.assertEqual(_evidence_span_years(pd.DataFrame(), windows), 5.0)


if __name__ == "__main__":
    unittest.main()
