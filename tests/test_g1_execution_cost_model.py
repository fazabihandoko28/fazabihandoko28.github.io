"""G1 execution cost accounting tests."""
import unittest
from hanz_app.research.g1_execution_cost_model import ExecutionCosts, reconcile_long_trade

class G1ExecutionCostModelTests(unittest.TestCase):
    def test_round_trip_fee_and_reconciliation(self):
        result = reconcile_long_trade(1000, 1020, 10000, 100000, ExecutionCosts(.0015, .0025, .001, .001))
        self.assertAlmostEqual(result["fee_rupiah"], 1001 * 10000 * .0015 + 1018.98 * 10000 * .0025)
        self.assertAlmostEqual(result["net_rupiah"], result["gross_rupiah"] - result["fee_rupiah"] - result["slippage_rupiah"])
        self.assertAlmostEqual(result["r_multiple"], result["gross_r_multiple"] - result["fee_r"] - result["slippage_r"])
    def test_flat_price_is_net_loss(self):
        self.assertLess(reconcile_long_trade(1000, 1000, 100, 10000, ExecutionCosts(.0015, .0025, .001, .001))["net_rupiah"], 0)
    def test_zero_cost_is_not_hidden(self):
        result = reconcile_long_trade(1000, 1100, 100, 10000, ExecutionCosts(0, 0, 0, 0))
        self.assertEqual(result["net_rupiah"], result["gross_rupiah"])
    def test_tiny_risk_cannot_emit_infinite_r(self):
        with self.assertRaisesRegex(ValueError, "Nonfinite execution cost R result"):
            reconcile_long_trade(1000, 1100, 100, 1e-320, ExecutionCosts(.0015, .0025, .001, .001))

    def test_invalid_inputs(self):
        for rate in (-.01, 1, float("nan"), float("inf"), True):
            with self.assertRaises(ValueError): ExecutionCosts(rate, .0025, .001, .001)
        with self.assertRaises(ValueError): reconcile_long_trade(1000, 1100, 1.5, 1000, ExecutionCosts(.001, .001, .001, .001))
        with self.assertRaises(ValueError): reconcile_long_trade(1000, 1100, 100, 0, ExecutionCosts(.001, .001, .001, .001))
