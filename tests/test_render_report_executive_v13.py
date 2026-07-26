from __future__ import annotations

import unittest

from hanz_app.render_report import render_report


class ExecutiveDashboardV13Tests(unittest.TestCase):
    def test_executive_decision_panel_and_mobile_layout(self) -> None:
        payload = {
            "generated_at": "2026-07-26T00:00:00+00:00",
            "source": {"name": "TEST", "grade": "RESEARCH", "delayed": True},
            "markets": [
                {
                    "market": "BEI",
                    "universe_size": 1,
                    "coverage_percent": 100,
                    "candidate_count": 1,
                    "reviewed_count": 0,
                    "rejected_count": 0,
                    "error_count": 0,
                    "candidates": [
                        {
                            "symbol": "TEST",
                            "market": "BEI",
                            "tier": "PRIMARY",
                            "entry_status": "WAIT",
                            "signal_close": 100,
                            "signal_timestamp": "2026-07-26",
                            "technical": {},
                            "evidence": {"positive": [], "neutral": [], "warning": [], "negative": [], "unknown": []},
                        }
                    ],
                    "reviewed": [],
                    "errors": [],
                }
            ],
        }
        output = render_report(payload)
        self.assertIn("TODAY'S DECISION", output)
        self.assertIn("WHAT TO DO", output)
        self.assertIn("quality-meter", output)
        self.assertIn("position:sticky", output)
        self.assertIn("INSTITUTIONAL RESEARCH DASHBOARD", output)


if __name__ == "__main__":
    unittest.main()
