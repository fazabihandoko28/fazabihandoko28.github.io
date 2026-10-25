"""G1 policy regression: five calendar years cannot be bypassed by overrides."""
import unittest

import pandas as pd

from hanz_app.research.hanz_walk_forward_evidence_validator import validate


def short_history_fixture():
    # All strategy metrics are otherwise healthy; only the OOS span is short.
    trades = pd.DataFrame({
        "trade_id": list(range(30)),
        "is_oos": [True] * 30,
        "r_multiple": [1.0] * 30,
        "trade_date": pd.date_range("2025-01-01", "2025-12-01", periods=30),
    })
    windows = pd.DataFrame({
        "window_id": ["w1", "w2"],
        "oos_profit_r": [15.0, 15.0],
        "is_profit_r": [15.0, 15.0],
        "is_years": [0.5, 0.5],
        "oos_years": [0.5, 0.5],
        "oos_start": ["2025-01-01", "2025-07-01"],
        "oos_end": ["2025-06-30", "2025-12-31"],
    })
    return trades, windows


class G1FiveYearHistoryFloorTests(unittest.TestCase):
    def test_override_cannot_reduce_five_year_floor(self):
        trades, windows = short_history_fixture()
        for override in (0, -1, 4.99, float("nan"), float("inf"), -float("inf")):
            with self.subTest(override=override):
                with self.assertRaisesRegex(ValueError, "minimum backtest history"):
                    validate(trades, windows, dof_remaining_pct=95,
                             min_backtest_years=override)

    def test_default_and_stricter_threshold_still_reject_short_history(self):
        trades, windows = short_history_fixture()
        for override in (5.0, 6.0):
            with self.subTest(override=override):
                result = validate(trades, windows, dof_remaining_pct=95,
                                  min_backtest_years=override)
                self.assertFalse(result["passed"])
                self.assertFalse(result["checks"]["five_year_history"])
                self.assertEqual(result["oos_trades"], 30)
                self.assertTrue(all(value for name, value in result["checks"].items()
                                    if name != "five_year_history"))


if __name__ == "__main__":
    unittest.main()
