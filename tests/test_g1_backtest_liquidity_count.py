"""G1: malformed zero-volume-day evidence must not enter Top 5 backtests."""
import unittest

from hanz_app.research.generate_top5_5y_backtest import (
    _eligible, _legacy_wait_eligible, _zero_volume_days20,
)


def row(value, action="WAIT"):
    risk = {
        "hanz_action": action,
        "canonical_rank_score": 80,
        "zero_volume_days20": value,
    }
    if action == "AVOID":
        risk.update({
            "rr_target_2": 2.5,
            "opportunity_score_breakdown": {"raw_score_before_action_cap": 40},
        })
    return {"ticker": "TEST", "risk_validation": risk}


class G1LiquidityEvidenceTests(unittest.TestCase):
    def test_malformed_explicit_counts_cannot_pass_top5_gate(self):
        # Previously int(4.9) == 4 and invalid/negative values defaulted to 0.
        for invalid in (4.9, "4.9", -1, 21, True, "nan", float("nan"),
                        float("inf"), "not-a-number"):
            with self.subTest(value=invalid):
                self.assertIsNone(_zero_volume_days20(row(invalid)["risk_validation"]))
                self.assertFalse(_eligible(row(invalid)))

    def test_valid_counts_keep_existing_threshold(self):
        for valid in (0, 4, "0", "4", None, ""):
            with self.subTest(value=valid):
                self.assertTrue(_eligible(row(valid)))
        for blocked in (5, 20, "5", "20"):
            with self.subTest(value=blocked):
                self.assertFalse(_eligible(row(blocked)))

    def test_legacy_avoid_to_wait_cannot_bypass_invalid_liquidity(self):
        self.assertTrue(_legacy_wait_eligible(row(4, "AVOID")))
        for invalid in (4.9, -1, True, float("nan")):
            with self.subTest(value=invalid):
                self.assertFalse(_legacy_wait_eligible(row(invalid, "AVOID")))
                self.assertFalse(_eligible(row(invalid, "AVOID")))


if __name__ == "__main__":
    unittest.main()
