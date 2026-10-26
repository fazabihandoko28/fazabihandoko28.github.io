"""G1: explicit invalid execution prices must not bypass Top 5 upside safety."""
import unittest
from hanz_app.research.generate_top5_5y_backtest import _eligible


def row(**overrides):
    base = {
        "ticker": "TEST",
        "risk_validation": {
            "hanz_action": "WAIT",
            "canonical_rank_score": 80,
            "zero_volume_days20": 0,
        },
        "entry_low": 100,
        "entry_high": 110,
        "target_1": 120,
    }
    base.update(overrides)
    return base


class G1BacktestPriceEvidenceTests(unittest.TestCase):
    def test_explicit_zero_or_negative_prices_fail_closed(self):
        for field in ("entry_low", "entry_high", "target_1"):
            for value in (0, -1, "0", "-1"):
                with self.subTest(field=field, value=value):
                    self.assertFalse(_eligible(row(**{field: value})))

    def test_reversed_entry_range_fails_closed(self):
        self.assertFalse(_eligible(row(entry_low=111, entry_high=110)))

    def test_valid_prices_and_legacy_missing_optional_price_preserved(self):
        self.assertTrue(_eligible(row()))
        self.assertFalse(_eligible(row(target_1=105)))
        candidate = row()
        candidate.pop("target_1")
        self.assertTrue(_eligible(candidate))


if __name__ == "__main__":
    unittest.main()
