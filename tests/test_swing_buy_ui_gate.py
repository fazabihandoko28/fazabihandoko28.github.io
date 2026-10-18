"""Regression guard for dashboard execution-safe labels."""
import unittest
from pathlib import Path


class SwingBuyUiGateTests(unittest.TestCase):
    def test_confirmed_buy_requires_execution_validation(self):
        html = (Path(__file__).resolve().parents[1] / "docs/dashboard/swing/index.html").read_text(encoding="utf-8")
        self.assertIn("const confirmed=all.filter(hanzExecutionEligible);", html)
        self.assertIn("const radar=all.filter(r=>!hanzExecutionEligible(r));", html)
        self.assertIn("const isBuy=hanzExecutionEligible(top);", html)
        self.assertIn("&& barDate===completedBarDate", html)


if __name__ == "__main__":
    unittest.main()
