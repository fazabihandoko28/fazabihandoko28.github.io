"""G1 regression: largest-winner concentration ceiling cannot be bypassed."""
import unittest

import pandas as pd

from hanz_app.research.hanz_walk_forward_evidence_validator import validate


def concentrated_fixture():
    # 30 OOS trades, positive expectancy, two profitable windows and six
    # calendar years. One 5R trade contributes >35% of all positive returns.
    trades = pd.DataFrame({
        "trade_id": list(range(30)),
        "is_oos": [True] * 30,
        "r_multiple": [5.0] + [0.2] * 29,
    })
    windows = pd.DataFrame({
        "window_id": ["w1", "w2"],
        "oos_profit_r": [5.4, 5.4],
        "is_profit_r": [4.0, 4.0],
        "is_years": [1.0, 1.0],
        "oos_years": [1.0, 1.0],
        "oos_start": ["2020-01-01", "2023-01-01"],
        "oos_end": ["2023-01-01", "2026-01-01"],
    })
    return trades, windows


class G1ConcentrationSafetyCeilingTests(unittest.TestCase):
    def test_weaker_override_cannot_certify_concentrated_strategy(self):
        trades, windows = concentrated_fixture()
        for override in (35.01, 50.0, 100.0, float("nan"), float("inf"),
                         -float("inf"), -1.0):
            with self.subTest(override=override):
                with self.assertRaisesRegex(ValueError, "maximum trade profit concentration"):
                    validate(trades, windows, 95.0, max_trade_profit_share_pct=override)

    def test_default_ceiling_rejects_concentrated_strategy(self):
        trades, windows = concentrated_fixture()
        report = validate(trades, windows, 95.0)
        self.assertGreater(report["max_trade_profit_share_pct"], 35.0)
        self.assertFalse(report["checks"]["profit_concentration"])
        self.assertFalse(report["passed"])
        self.assertTrue(all(value for name, value in report["checks"].items()
                            if name != "profit_concentration"))

    def test_stricter_ceiling_remains_allowed(self):
        trades, windows = concentrated_fixture()
        report = validate(trades, windows, 95.0, max_trade_profit_share_pct=25.0)
        self.assertEqual(report["policy"]["max_trade_profit_share_pct"], 25.0)
        self.assertFalse(report["checks"]["profit_concentration"])


if __name__ == "__main__":
    unittest.main()
