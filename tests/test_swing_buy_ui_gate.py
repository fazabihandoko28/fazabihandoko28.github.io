"""Regression checks: dashboard BUY labels must fail closed."""
import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path

PAGE = Path(__file__).resolve().parents[1] / "docs/dashboard/swing/index.html"


class SwingBuyUiGateTests(unittest.TestCase):
    def test_confirmed_list_and_hero_use_execution_gate(self):
        html = PAGE.read_text(encoding="utf-8")
        self.assertIn("const confirmed=all.filter(hanzExecutionEligible);", html)
        self.assertIn("const radar=all.filter(r=>!hanzExecutionEligible(r));", html)
        self.assertIn("const isBuy=hanzExecutionEligible(top);", html)
        self.assertIn("&& barDate===completedBarDate", html)

    @unittest.skipUnless(shutil.which("node"), "Node.js unavailable")
    def test_execution_gate_behavior(self):
        html = PAGE.read_text(encoding="utf-8")
        match = re.search(
            r"(function hanzExecutionEligible\\(row\\)\\{.*?\\n\\})\\s*function effectiveHanzAction",
            html, re.S,
        )
        self.assertIsNotNone(match, "Execution gate function not found")
        function_js = match.group(1)
        script = function_js + """
const riskObject = row => row.risk_validation || {};
const idxStatusNow = () => ({reason:"Weekend",parts:{iso:"2026-10-18",minutes:1300}});
const nearestTradingDay = () => "2026-10-16";
const row = {
  state:"SWING_BUY",risk_gate:"ELIGIBLE",entry_status:"ENTRY_ZONE",
  daily_bar_at:"2026-10-16T00:00:00Z",
  risk_validation:{
    actionable:true,
    data_quality:{verified:true,status:"VERIFIED",verifier_source:"INDEPENDENT",
      primary_date:"2026-10-16",verifier_date:"2026-10-16"}
  }
};
const assert = (ok, label) => { if(!ok) throw Error(label); };
assert(hanzExecutionEligible(row)===true,"fully verified fresh candidate");
assert(hanzExecutionEligible({...row,risk_gate:"BLOCKED"})===false,"blocked gate");
assert(hanzExecutionEligible({...row,daily_bar_at:"2026-10-09",
  risk_validation:{...row.risk_validation,data_quality:{
    ...row.risk_validation.data_quality,primary_date:"2026-10-09",verifier_date:"2026-10-09"
  }}})===false,"stale bar");
assert(hanzExecutionEligible({...row,risk_validation:{
  ...row.risk_validation,data_quality:{...row.risk_validation.data_quality,verified:false}
}})===false,"unverified source");
"""
        proc = subprocess.run(["node", "-e", script], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)


if __name__ == "__main__":
    unittest.main()
