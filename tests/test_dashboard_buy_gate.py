"""Regression checks: technical BUY must not bypass independent execution gates."""
from __future__ import annotations

import pathlib
import subprocess
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
DASHBOARD = ROOT / "docs/dashboard/swing/index.html"


class DashboardBuyGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = DASHBOARD.read_text(encoding="utf-8")

    def test_all_buy_surfaces_use_execution_gate(self):
        html = self.html
        confirmed = html.split("  const confirmed=all\n", 1)[1].split(
            '  $("opportunityCount")', 1
        )[0]
        self.assertIn("hanzExecutionEligible(r)", confirmed)
        self.assertIn("const radar=all.filter(r=>!confirmed.includes(r));", confirmed)
        self.assertIn("const isBuy=confirmed.includes(top);", html)

    def test_gate_requires_strategy_freshness_and_independent_data(self):
        html = self.html
        helper = "function hanzExecutionEligible(row){" + html.split(
            "function hanzExecutionEligible(row){", 1
        )[1].split("\nfunction effectiveHanzAction(", 1)[0]
        js = """
function riskObject(row){return row.risk_validation||{};}
function hanzIndexObservation(){return {};}
let indexStatus="PRICE_FRESH";
function hanzIndexFreshness(){return indexStatus;}
""" + helper + """
const base={state:"SWING_BUY",risk_gate:"ELIGIBLE",
  entry_status:"ENTRY_ZONE",daily_bar_at:"2026-10-19",
  risk_validation:{gate:"ELIGIBLE",actionable:true,
    data_expected_completed_date:"2026-10-19",
    strategy_validation:{passed:true},
    data_quality:{verified:true,status:"VERIFIED",
      verifier_source:"INDEPENDENT",primary_date:"2026-10-19",
      verifier_date:"2026-10-19"}}};
function check(label,row,expected){
  if(hanzExecutionEligible(row)!==expected) throw Error(label);
}
check("verified",base,true);
check("blocked",{...base,risk_gate:"BLOCKED"},false);
check("no_strategy",{...base,risk_validation:{...base.risk_validation,
  strategy_validation:{passed:false}}},false);
check("stale_bar",{...base,daily_bar_at:"2026-10-16"},false);
check("no_verifier",{...base,risk_validation:{...base.risk_validation,
  data_quality:{...base.risk_validation.data_quality,verified:false}}},false);
indexStatus="PRICE_UNVERIFIED";
check("stale_ihsg",base,false);
"""
        result = subprocess.run(
            ["node", "-e", js], capture_output=True, text=True, check=False
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
