"""G1 regression: nonfinite monitor scores cannot be promoted into Top 5."""
import unittest

from hanz_app.research.generate_top5_5y_backtest import _eligible, _num, _rank


class G1BacktestNonfiniteRankTests(unittest.TestCase):
    @staticmethod
    def row(score):
        return {
            "ticker": "BAD",
            "hanz_action": "WAIT",
            "risk_validation": {
                "hanz_action": "WAIT",
                "canonical_rank_score": score,
            },
        }

    def test_nan_or_infinity_cannot_become_top_ranked(self):
        # Before fix, max(0, min(100, float("nan"))) == 100,
        # so corrupt provider scores could be selected as Top 5.
        for invalid in ("NaN", "Infinity", "-Infinity",
                        float("nan"), float("inf"), float("-inf")):
            with self.subTest(score=str(invalid)):
                self.assertIsNone(_num(invalid))
                row = self.row(invalid)
                self.assertEqual(_rank(row), 0)
                self.assertFalse(_eligible(row))

    def test_valid_finite_scores_keep_existing_ranking(self):
        for score, expected in (("45.5", 45.5), (65, 65), (120, 100), (-3, 0)):
            with self.subTest(score=score):
                row = self.row(score)
                self.assertEqual(_rank(row), expected)
                self.assertEqual(_eligible(row), expected > 0)


    def test_boolean_rank_cannot_enter_top5(self):
        # Previously float(True) == 1.0 made malformed score evidence eligible.
        for invalid in (True, False):
            with self.subTest(score=invalid):
                self.assertIsNone(_num(invalid))
                row = self.row(invalid)
                self.assertEqual(_rank(row), 0)
                self.assertFalse(_eligible(row))
        # Ordinary finite scores retain their previous eligibility.
        self.assertTrue(_eligible(self.row(1)))


if __name__ == "__main__":
    unittest.main()
