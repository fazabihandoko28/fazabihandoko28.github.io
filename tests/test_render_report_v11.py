from __future__ import annotations

import unittest

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))
from hanz_app.render_report import render_report


class RenderReportV11Tests(unittest.TestCase):
    def test_report_contains_quality_plan_and_market_posture(self) -> None:
        payload = {
            "generated_at": "2026-07-26T12:00:00+00:00",
            "source": {"name": "yahoo_finance", "grade": "RESEARCH", "delayed": True},
            "markets": [{
                "market": "BEI", "universe_size": 30, "analysis_count": 30, "coverage_percent": 100.0,
                "candidate_count": 1, "reviewed_count": 0, "rejected_count": 29, "error_count": 0,
                "candidates": [{
                    "market": "BEI", "symbol": "PTBA", "tier": "PRIMARY", "entry_status": "READY", "vetoes": [],
                    "selection_reasons": ["Core evidence aligned"], "rejection_reasons": [], "signal_close": 2500,
                    "signal_timestamp": "2026-07-26T00:00:00+00:00",
                    "technical": {"rsi14": 61.4, "atr14": 80, "support20": 2380, "relative_volume20": 1.8, "resistance20": 2600},
                    "evidence": {"positive": ["data_freshness", "liquidity", "risk_reward", "market_regime", "price_structure", "volume_confirmation"], "neutral": ["resistance", "extension_risk"], "warning": [], "negative": [], "unknown": []},
                }], "reviewed": [], "rejected": [], "errors": [],
            }],
        }
        output = render_report(payload)
        self.assertIn("QUALITY", output)
        self.assertIn("MARKET POSTURE", output)
        self.assertIn("Entry zone", output)
        self.assertIn("TARGET 1", output)
        self.assertNotIn("win probability", output.lower())


if __name__ == "__main__":
    unittest.main()
