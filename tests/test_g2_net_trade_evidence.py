"""G2 cost integration: no fabricated broker fees, no BUY/OOS certification."""
import unittest

from hanz_app.research.g2_net_trade_evidence import net_trade_evidence


class G2CostIntegrationTests(unittest.TestCase):
    def test_reconcile_positive_gross_with_costs(self):
        rows = [{"trade_id": "verified-1", "is_oos": True,
                 "buy_price": 1000, "sell_price": 1100, "shares": 100,
                 "initial_risk_rupiah": 5000}]
        result = net_trade_evidence(rows, buy_fee_rate=.001,
            sell_fee_rate=.002, buy_slippage_rate=.001,
            sell_slippage_rate=.001, assumption_source="research sensitivity scenario")
        trade = result["trades"][0]
        self.assertAlmostEqual(trade["gross_r_multiple"], 2.0)
        self.assertLess(trade["r_multiple"], trade["gross_r_multiple"])
        self.assertAlmostEqual(trade["net_rupiah"],
            trade["gross_rupiah"] - trade["fee_rupiah"] - trade["slippage_rupiah"])
        self.assertFalse(result["buy_authorized"])
        self.assertFalse(result["oos_certified"])

    def test_requires_source(self):
        with self.assertRaises(ValueError):
            net_trade_evidence([], buy_fee_rate=0, sell_fee_rate=0,
                buy_slippage_rate=0, sell_slippage_rate=0, assumption_source="")

    def test_refuses_unverified_trade(self):
        with self.assertRaises(ValueError):
            net_trade_evidence([{"trade_id": "x", "is_oos": False}],
                buy_fee_rate=0, sell_fee_rate=0, buy_slippage_rate=0,
                sell_slippage_rate=0, assumption_source="test")

    def test_refuses_duplicate_trade(self):
        trade = {"trade_id": "x", "is_oos": True, "buy_price": 100,
                 "sell_price": 110, "shares": 10, "initial_risk_rupiah": 20}
        with self.assertRaises(ValueError):
            net_trade_evidence([trade, trade], buy_fee_rate=0, sell_fee_rate=0,
                buy_slippage_rate=0, sell_slippage_rate=0, assumption_source="test")

    def test_refuses_invalid_cost(self):
        with self.assertRaises(ValueError):
            net_trade_evidence([], buy_fee_rate=float("nan"), sell_fee_rate=0,
                buy_slippage_rate=0, sell_slippage_rate=0, assumption_source="test")


if __name__ == "__main__":
    unittest.main()
