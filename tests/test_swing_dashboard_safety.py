import unittest
from pathlib import Path

HTML = (Path(__file__).resolve().parents[1] / "docs/dashboard/swing/index.html").read_text()


class DashboardExecutionSafetyTests(unittest.TestCase):
    def test_confirmed_buy_requires_execution_gate(self):
        self.assertIn('function hanzConfirmedBuy(row){', HTML)
        self.assertIn('includes(state) && hanzExecutionEligible(row)', HTML)
        self.assertIn('const confirmed=all.filter(hanzConfirmedBuy);', HTML)
        self.assertIn('const radar=all.filter(r=>!hanzConfirmedBuy(r));', HTML)
        self.assertIn('const isBuy=hanzConfirmedBuy(top);', HTML)

    def test_zero_volume_tail_not_presented_as_fresh_trading(self):
        self.assertIn('const lastTradedIndex=rows.findLastIndex(', HTML)
        self.assertIn('c.volume>0', HTML)
        self.assertIn('const data=traded.slice(-60);', HTML)
        self.assertIn('UNVERIFIED ZERO-VOLUME BARS:', HTML)
        self.assertIn('Unverified tail excluded; NOT LIVE', HTML)
        self.assertIn('return `${chartWarning}<div class="tech-chart-grid">', HTML)


if __name__ == "__main__":
    unittest.main()
