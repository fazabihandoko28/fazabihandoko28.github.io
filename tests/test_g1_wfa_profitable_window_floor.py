"""G1 regression: profitable walk-forward windows cannot be overridden below 50%."""
import unittest

import pandas as pd

from hanz_app.research.hanz_walk_forward_evidence_validator import validate


def weak_consistency_fixture():
    # Only one of four windows is profitable (25%). All other G1 checks pass.
    # Trade-level P&L sums to the same 7 R as the four window results.
    trades = pd.DataFrame({
        "window_id": ["w1"] * 20 + ["w2"] * 3 + ["w3"] * 3 + ["w4"] * 4,
        "trade_id": list(range(30)),
        "is_oos": [True] * 30,
        "r_multiple": [0.5] * 20 + [-0.3] * 10,
    })
    windows = pd.DataFrame({
        "window_id": ["w1", "w2", "w3", "w4"],
        "oos_profit_r": [10.0, -0.9, -0.9, -1.2],
        "is_profit_r": [2.0] * 4,
        "is_years": [1.0] * 4,
        "oos_years": [1.0] * 4,
        "oos_start": ["2020-01-01", "2021-07-01", "2023-01-02", "2024-07-02"],
        "oos_end": ["2021-06-30", "2023-01-01", "2024-07-01", "2026-01-01"],
    })
    return trades, windows


class G1ProfitableWindowFloorTests(unittest.TestCase):
    def test_lower_override_cannot_certify_strategy(self):
        trades, windows = weak_consistency_fixture()
        for override in (0.0, -1.0, 49.9, float("nan"), float("inf"), -float("inf")):
            with self.subTest(override=override):
                with self.assertRaisesRegex(ValueError, "minimum profitable walk-forward windows"):
                    validate(trades, windows, 95.0, min_profitable_windows_pct=override)

    def test_default_floor_rejects_weak_consistency(self):
        trades, windows = weak_consistency_fixture()
        report = validate(trades, windows, 95.0)
        self.assertEqual(report["profitable_wf_pct"], 25.0)
        self.assertFalse(report["checks"]["profitable_window_consistency"])
        self.assertFalse(report["passed"])
        self.assertTrue(all(value for name, value in report["checks"].items()
                            if name != "profitable_window_consistency"))

    def test_stricter_floor_is_allowed(self):
        trades, windows = weak_consistency_fixture()
        report = validate(trades, windows, 95.0, min_profitable_windows_pct=75.0)
        self.assertEqual(report["policy"]["min_profitable_windows_pct"], 75.0)
        self.assertFalse(report["checks"]["profitable_window_consistency"])


if __name__ == "__main__":
    unittest.main()
