import re
import unittest
from pathlib import Path

HTML = (Path(__file__).resolve().parents[1] / "docs/dashboard/swing/index.html").read_text(encoding="utf-8")


class DashboardVerifiedBuyGateTest(unittest.TestCase):
    def test_independent_verification_is_required_for_buy(self):
        self.assertIn('function hanzExecutionEligible(row)', HTML)
        self.assertIn('&& r.actionable===true', HTML)
        self.assertIn('&& quality.verified===true', HTML)
        self.assertIn('&& Boolean(quality.verifier_source)', HTML)
        self.assertIn('&& String(row?.entry_status || "").toUpperCase()==="ENTRY_ZONE"', HTML)

    def test_confirmed_buy_section_requires_execution_gate(self):
        self.assertRegex(HTML, r'const confirmed=all\s*\.filter\(r=>hanzExecutionEligible\(r\) &&')
        self.assertNotRegex(HTML, r'const confirmed=all\s*\.filter\(r=>\["EARLY_CONFIRMED_BUY"')

    def test_blocked_technical_buy_remains_visible_as_radar(self):
        self.assertRegex(HTML, r'const radar=all\s*\.filter\(r=>!hanzExecutionEligible\(r\) \|\|')
        self.assertIn('const isBuy=hanzExecutionEligible(top) &&', HTML)

    def test_static_headings_do_not_promise_buy(self):
        self.assertIn('<span>TOP SWING OPPORTUNITY</span>', HTML)
        self.assertIn('<span>VERIFIED BUY</span>', HTML)
        self.assertNotIn('<span>CURRENT TOP SWING BUY</span>', HTML)


if __name__ == "__main__":
    unittest.main()
