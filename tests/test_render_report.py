from __future__ import annotations

import unittest

from bootstrap import PROJECT_ROOT  # noqa: F401

from hanz_app.render_report import render_report


class RenderReportTests(unittest.TestCase):
    def test_report_contains_candidate_and_research_warning(self) -> None:
        payload = {
            "generated_at": "2026-07-25T12:00:00+00:00",
            "source": {"name": "yahoo_finance", "grade": "RESEARCH", "delayed": True},
            "markets": [
                {
                    "market": "BEI",
                    "universe_size": 10,
                    "candidate_count": 1,
                    "rejected_count": 4,
                    "error_count": 0,
                    "candidates": [
                        {
                            "market": "BEI",
                            "symbol": "PTBA",
                            "tier": "PRIMARY",
                            "entry_status": "READY",
                            "selection_reasons": ["Core evidence aligned"],
                            "rejection_reasons": [],
                            "signal_close": 2500,
                            "signal_timestamp": "2026-07-25T00:00:00+00:00",
                            "evidence": {"positive": ["liquidity"], "warning": [], "negative": [], "unknown": []},
                        }
                    ],
                }
            ],
        }
        output = render_report(payload)
        self.assertIn("PTBA", output)
        self.assertIn("READY", output)
        self.assertIn("PAPER-TRADE RESEARCH ONLY", output)
        self.assertIn("HANZ isn't loyal to stocks", output)


if __name__ == "__main__":
    unittest.main()
