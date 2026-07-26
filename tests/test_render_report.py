from __future__ import annotations

import unittest

from bootstrap import PROJECT_ROOT  # noqa: F401
from hanz_app.render_report import render_report


class RenderReportTests(unittest.TestCase):
    def _payload(self) -> dict:
        return {
            "generated_at": "2026-07-26T12:00:00+00:00",
            "source": {"name": "yahoo_finance", "grade": "RESEARCH", "delayed": True},
            "markets": [{
                "market": "BEI", "universe_size": 30, "analysis_count": 29, "coverage_percent": 96.7,
                "candidate_count": 1, "reviewed_count": 1, "rejected_count": 27, "error_count": 1,
                "candidates": [{
                    "market": "BEI", "symbol": "PTBA", "tier": "PRIMARY", "entry_status": "READY",
                    "selection_reasons": ["Core evidence aligned"], "rejection_reasons": [], "signal_close": 2500,
                    "signal_timestamp": "2026-07-26T00:00:00+00:00",
                    "technical": {"rsi14": 61.4, "relative_volume20": 1.8, "resistance20": 2600},
                    "evidence": {"positive": ["liquidity", "price_structure", "volume_confirmation", "risk_reward"], "neutral": ["resistance"], "warning": [], "negative": [], "unknown": []},
                }],
                "reviewed": [{
                    "market": "BEI", "symbol": "BBCA", "tier": "SECONDARY", "entry_status": "WAIT",
                    "selection_reasons": ["Evidence retained for confirmation"], "rejection_reasons": [], "signal_close": 9000,
                    "signal_timestamp": "2026-07-26T00:00:00+00:00", "technical": {},
                    "evidence": {"positive": ["liquidity"], "neutral": ["price_structure"], "warning": ["resistance"], "negative": [], "unknown": []},
                }],
                "errors": [{"symbol": "TEST", "error": "fetch failed"}],
            }],
        }

    def test_report_contains_candidate_watchlist_and_research_warning(self) -> None:
        output = render_report(self._payload())
        self.assertIn("PTBA", output)
        self.assertIn("BBCA", output)
        self.assertIn("Top developing watchlist", output)
        self.assertIn("PAPER-TRADE RESEARCH ONLY", output)
        self.assertIn("96.7% analyzed", output)
        self.assertIn("Resistance", output)

    def test_report_does_not_claim_probability(self) -> None:
        output = render_report(self._payload())
        self.assertNotIn("confidence %", output.lower())
        self.assertNotIn("probability", output.lower())


if __name__ == "__main__":
    unittest.main()
