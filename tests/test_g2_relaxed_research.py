import unittest
from hanz_app.research.generate_top5_5y_backtest import (
    _eligible, _research_only_eligible, _research_candidates
)


def row(ticker="TEST", action="AVOID", value=60000000, zero=6):
    return {"ticker": ticker, "risk_validation": {
        "hanz_action": action, "avg_value20": value,
        "zero_volume_days20": zero, "momentum_guard": {"blocked": True},
        "volatility_status": "NORMAL"}}


class RelaxedResearchTests(unittest.TestCase):
    def test_avoid_is_research_only(self):
        candidate = row()
        self.assertTrue(_research_only_eligible(candidate))
        self.assertFalse(_eligible(candidate))

    def test_below_fifty_million_rejected(self):
        self.assertFalse(_research_only_eligible(row(value=49000000)))

    def test_seven_zero_volume_days_rejected(self):
        self.assertFalse(_research_only_eligible(row(zero=7)))

    def test_extreme_volatility_rejected(self):
        candidate = row()
        candidate["risk_validation"]["volatility_status"] = "EXTREME"
        self.assertFalse(_research_only_eligible(candidate))

    def test_research_candidates_dont_change_production_selection(self):
        candidate = row()
        self.assertEqual(_research_candidates([], [candidate]), ["TEST"])
        self.assertFalse(_eligible(candidate))


if __name__ == "__main__":
    unittest.main()
