from __future__ import annotations

import unittest

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))
from hanz_app.decision_intelligence import evidence_quality, market_health, quality_grade, trade_plan


class DecisionIntelligenceTests(unittest.TestCase):
    def _ready(self) -> dict:
        return {
            "entry_status": "READY", "vetoes": [], "signal_close": 100.0,
            "technical": {"atr14": 4.0, "support20": 94.0, "resistance20": 108.0},
            "evidence": {
                "positive": ["data_freshness", "liquidity", "risk_reward", "market_regime", "price_structure", "volume_confirmation"],
                "neutral": ["resistance", "extension_risk"], "warning": [], "negative": [], "unknown": [],
            },
        }

    def test_quality_is_not_probability_and_is_bounded(self) -> None:
        score = evidence_quality(self._ready())
        self.assertGreaterEqual(score, 0)
        self.assertLessEqual(score, 100)
        self.assertIn(quality_grade(score, "READY"), {"AAA", "AA", "A", "BBB", "BB", "WATCH"})

    def test_trade_plan_uses_atr_and_support(self) -> None:
        plan = trade_plan(self._ready())
        self.assertTrue(plan.valid)
        self.assertLess(plan.stop, plan.entry_low)
        self.assertGreater(plan.target_1, plan.entry_high)
        self.assertGreaterEqual(plan.reward_risk_1, 1.8)

    def test_market_health_is_conservative_when_data_limited(self) -> None:
        health = market_health({"universe_size": 30, "error_count": 10, "candidates": [], "reviewed": [], "rejected_count": 20})
        self.assertEqual(health["label"], "DATA LIMITED")
        self.assertEqual(health["paper_exposure_percent"], 0)


if __name__ == "__main__":
    unittest.main()
