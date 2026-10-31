"""G1 CLI certification must reject missing or contradictory execution costs."""
import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import pandas as pd

from hanz_app.research.hanz_walk_forward_evidence_validator import (
    main, require_execution_cost_evidence,
)


class G1ExecutionCostEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.trades = pd.DataFrame({
            "is_oos": [True, True, False],
            "r_multiple": [0.94, -1.06, 3.0],
            "gross_r_multiple": [1.0, -1.0, 3.0],
            "fee_r": [0.02, 0.02, None],
            "slippage_r": [0.04, 0.04, None],
        })

    def test_reconciled_net_returns(self):
        require_execution_cost_evidence(self.trades)

    def test_missing_cost_column(self):
        with self.assertRaisesRegex(ValueError, "Missing G1 execution cost"):
            require_execution_cost_evidence(self.trades.drop(columns="fee_r"))

    def test_gross_only_return_rejected(self):
        bad = self.trades.copy()
        bad.loc[0, "r_multiple"] = 1.0
        with self.assertRaisesRegex(ValueError, "does not reconcile"):
            require_execution_cost_evidence(bad)

    def test_negative_slippage_rejected(self):
        bad = self.trades.copy()
        bad.loc[0, "slippage_r"] = -0.04
        with self.assertRaisesRegex(ValueError, "Negative G1"):
            require_execution_cost_evidence(bad)

    def test_missing_fee_value_rejected(self):
        bad = self.trades.copy()
        bad.loc[0, "fee_r"] = float("nan")
        with self.assertRaisesRegex(ValueError, "Invalid G1 execution cost"):
            require_execution_cost_evidence(bad)

    def test_boolean_fee_rejected(self):
        bad = self.trades.astype({"fee_r": object})
        bad.loc[0, "fee_r"] = True
        with self.assertRaisesRegex(ValueError, "Invalid G1 execution cost"):
            require_execution_cost_evidence(bad)

    def test_no_oos_evidence_rejected(self):
        bad = self.trades.copy()
        bad["is_oos"] = False
        with self.assertRaisesRegex(ValueError, "Missing G1 OOS"):
            require_execution_cost_evidence(bad)

    def test_infinite_gross_rejected(self):
        bad = self.trades.copy()
        bad.loc[0, "gross_r_multiple"] = float("inf")
        with self.assertRaisesRegex(ValueError, "Invalid G1 execution cost"):
            require_execution_cost_evidence(bad)

    def test_invalid_oos_flag_rejected(self):
        bad = self.trades.astype({"is_oos": object})
        bad.loc[0, "is_oos"] = "maybe"
        with self.assertRaisesRegex(ValueError, "Invalid G1 execution cost OOS"):
            require_execution_cost_evidence(bad)

    def test_cli_fails_closed_on_missing_costs(self):
        with tempfile.TemporaryDirectory() as temp:
            trade_path = Path(temp) / "trades.csv"
            window_path = Path(temp) / "windows.csv"
            pd.DataFrame({"is_oos": [True], "r_multiple": [1.0]}).to_csv(trade_path, index=False)
            pd.DataFrame({"window_id": ["W1"], "oos_profit_r": [1.0]}).to_csv(window_path, index=False)
            argv = ["validator", "--trades", str(trade_path), "--windows",
                    str(window_path), "--dof-remaining-pct", "95"]
            with mock.patch.object(sys, "argv", argv):
                with self.assertRaisesRegex(ValueError, "Missing G1 execution cost"):
                    main()

    def test_cli_accepts_cost_schema_but_does_not_certify_short_history(self):
        with tempfile.TemporaryDirectory() as temp:
            trade_path = Path(temp) / "trades.csv"
            window_path = Path(temp) / "windows.csv"
            self.trades.loc[:0].to_csv(trade_path, index=False)
            pd.DataFrame({"window_id": ["W1"], "oos_profit_r": [0.94]}).to_csv(window_path, index=False)
            argv = ["validator", "--trades", str(trade_path), "--windows",
                    str(window_path), "--dof-remaining-pct", "95"]
            with mock.patch.object(sys, "argv", argv), contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaises(SystemExit) as exited:
                    main()
            self.assertEqual(exited.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
