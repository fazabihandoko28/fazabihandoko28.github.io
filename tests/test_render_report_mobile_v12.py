import unittest
from hanz_app.render_report import render_report

class MobileReportTests(unittest.TestCase):
    def test_mobile_experience_css_and_decision_card_are_rendered(self):
        payload = {
            "generated_at": "2026-07-26T00:00:00+00:00",
            "source": {"name": "TEST", "grade": "RESEARCH", "delayed": True},
            "markets": [{
                "market": "BEI", "universe_size": 1, "coverage_percent": 100,
                "candidate_count": 0, "reviewed_count": 0, "rejected_count": 1,
                "error_count": 0, "candidates": [], "reviewed": [], "errors": [],
            }],
        }
        result = render_report(payload)
        self.assertIn('class="mobile-decision"', result)
        self.assertIn('scroll-snap-type:x mandatory', result)
        self.assertIn('@media(max-width:720px)', result)
        self.assertIn('STAY CASH', result)

if __name__ == "__main__":
    unittest.main()
