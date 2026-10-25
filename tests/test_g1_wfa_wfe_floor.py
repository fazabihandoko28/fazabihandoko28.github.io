"""G1 policy regression: the 0.50 WFE safety floor is non-bypassable."""
import unittest

import pandas as pd

from hanz_app.research.hanz_walk_forward_evidence_validator import validate


def weak_wfe_fixture():
    # Other gates are healthy; annualized OOS profit is only 25% of IS.
    trades = pd.DataFrame({
        "is_oos": [True] * 30,
        "r_multiple": [1.0 / 3] * 30,
    })
    windows = pd.DataFrame({
        "window_id": ["w1", "w2"],
        "oos_profit_r": [5.0, 5.0],
        "is_profit_r": [20.0, 20.0],
        "is_years": [1.0, 1.0],
        "oos_years": [1.0, 1.0],
        "oos_start": ["2020-01-01", "2023-01-01"],
        "oos_end": ["2023-01-01", "2026-01-01"],
    })
    return trades, windows


class G1WFEFloorTests(unittest.TestCase):
    def test_weaker_wfe_override_cannot_certify_strategy(self):
        trades, windows = weak_wfe_fixture()
        for override in (0, -1, 0.1, 0.49, float("nan"), float("inf"), -float("inf")):
            with self.subTest(override=override):
                with self.assertRaisesRegex(ValueError, "minimum WFE"):
                    validate(trades, windows, 95.0, min_wfe=override)

    def test_default_floor_rejects_underperforming_oos(self):
        trades, windows = weak_wfe_fixture()
        report = validate(trades, windows, 95.0)
        self.assertAlmostEqual(report["wfe"], 0.25)
        self.assertFalse(report["checks"]["wfe"])
        self.assertFalse(report["passed"])
        self.assertTrue(all(value for name, value in report["checks"].items()
                            if name != "wfe"))

    def test_stricter_floor_remains_allowed(self):
        trades, windows = weak_wfe_fixture()
        report = validate(trades, windows, 95.0, min_wfe=0.8)
        self.assertEqual(report["policy"]["min_wfe"], 0.8)
        self.assertFalse(report["checks"]["wfe"])


if __name__ == "__main__":
    unittest.main()
