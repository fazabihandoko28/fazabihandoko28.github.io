"""G1 regression: finite source values cannot overflow into a false WFA PASS."""
import unittest
import warnings

import pandas as pd

from hanz_app.research.hanz_walk_forward_evidence_validator import validate


class G1NonfiniteDerivedEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.trades = pd.DataFrame({
            "trade_id": list(range(30)),
            "is_oos": [True] * 30,
            "r_multiple": [1.0] * 30,
        })
        self.windows = pd.DataFrame({
            "window_id": ["W1", "W2"],
            "oos_profit_r": [15.0, 15.0],
            "is_profit_r": [15.0, 15.0],
            "is_years": [1.0, 1.0],
            "oos_years": [1.0, 1.0],
            "oos_start": ["2020-01-01", "2023-01-01"],
            "oos_end": ["2022-12-31", "2026-01-01"],
        })

    def test_finite_normal_metrics_remain_eligible(self):
        report = validate(self.trades, self.windows, 95.0)
        self.assertTrue(report["passed"])
        self.assertTrue(report["checks"]["five_year_history"])

    def test_finite_input_overflow_cannot_certify_wfa(self):
        # Before the guard, 30 finite 1e308 trades produce infinite
        # expectancy/WFE and positive-R sum, but all strategy gates PASS.
        trades = self.trades.assign(r_multiple=[1e308] * 30)
        windows = self.windows.assign(
            oos_profit_r=[1e308, 1e308], is_profit_r=[1.0, 1.0]
        )
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            with self.assertRaisesRegex(ValueError, "Nonfinite walk-forward derived evidence"):
                validate(trades, windows, 95.0)


if __name__ == "__main__":
    unittest.main()
