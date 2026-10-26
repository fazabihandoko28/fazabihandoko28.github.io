"""G1 Top 5: malformed explicit average-traded-value evidence must fail closed."""
import unittest

from hanz_app.research.generate_top5_5y_backtest import (
    _eligible, _legacy_wait_eligible,
)


def row(avg, action="WAIT"):
    risk = {
        "hanz_action": action,
        "canonical_rank_score": 80,
        "zero_volume_days20": 0,
        "avg_value20": avg,
    }
    if action == "AVOID":
        risk.update({
            "rr_target_2": 2.5,
            "opportunity_score_breakdown": {"raw_score_before_action_cap": 40},
        })
    return {"ticker": "TEST", "risk_validation": risk}


class G1AverageTradedValueEvidenceTests(unittest.TestCase):
    def test_explicit_malformed_avg_value_cannot_pass_top5(self):
        for value in ("not-a-number", "NaN", "Infinity", True, False,
                      "", float("nan"), float("inf")):
            with self.subTest(value=value):
                self.assertFalse(_eligible(row(value)))

    def test_invalid_avg_cannot_promote_legacy_avoid(self):
        for value in ("NaN", True, "bad"):
            with self.subTest(value=value):
                self.assertFalse(_legacy_wait_eligible(row(value, "AVOID")))
                self.assertFalse(_eligible(row(value, "AVOID")))

    def test_valid_avg_threshold_unchanged(self):
        for value in (100_000_000, "100000000", 200_000_000):
            with self.subTest(value=value):
                self.assertTrue(_eligible(row(value)))
                self.assertTrue(_legacy_wait_eligible(row(value, "AVOID")))
        for value in (0, 99_999_999):
            with self.subTest(value=value):
                self.assertFalse(_eligible(row(value)))
                self.assertFalse(_legacy_wait_eligible(row(value, "AVOID")))

    def test_missing_optional_avg_preserved(self):
        for action in ("WAIT", "AVOID"):
            candidate = row(None, action)
            candidate["risk_validation"].pop("avg_value20")
            self.assertTrue(_eligible(candidate))
            self.assertTrue(_eligible(row(None, action)))


if __name__ == "__main__":
    unittest.main()
