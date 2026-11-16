"""Regression checks for PIT ranking, OOS chronology, and net costs."""
import unittest
import pandas as pd
from hanz_app.research.g1_pit_oos_cost_replay import replay

class PITReplayTests(unittest.TestCase):
    def setUp(self):
        dates=pd.date_range("2025-01-01",periods=20,freq="D")
        self.bars=pd.DataFrame([
            {"symbol":symbol,"date":date,"open":price,"close":price,"volume":1000}
            for symbol,price in (("AAA",100),("BBB",200))
            for date in dates
        ])
        self.snap=pd.DataFrame([
            {"asof_date":dates[4],"symbol":"AAA","eligible":True,"rank_score":99},
            {"asof_date":dates[4],"symbol":"BBB","eligible":True,"rank_score":10},
            {"asof_date":dates[8],"symbol":"AAA","eligible":True,"rank_score":10},
            {"asof_date":dates[8],"symbol":"BBB","eligible":True,"rank_score":99},
            {"asof_date":dates[12],"symbol":"AAA","eligible":True,"rank_score":99},
            {"asof_date":dates[12],"symbol":"BBB","eligible":True,"rank_score":10},
        ])
    def test_asof_selection_never_uses_future_ranking(self):
        out=replay(self.bars,self.snap,train_days=5,test_days=4,hold_days=1,top_n=1)
        self.assertEqual(out["windows"][0]["selected_symbols"],["AAA"])
        self.assertEqual(out["windows"][1]["selected_symbols"],["BBB"])
        self.assertEqual(out["summary"]["missing_pit_windows"],1)
    def test_net_return_deducts_both_sides(self):
        out=replay(self.bars,self.snap,train_days=5,test_days=4,hold_days=1,top_n=1)
        trade=out["trades"][0]
        self.assertEqual(trade["gross_return_pct"],0)
        self.assertLess(trade["net_return_pct"],0)
    def test_missing_snapshot_not_silently_backfilled(self):
        out=replay(self.bars,self.snap.iloc[0:0],train_days=5,test_days=4,hold_days=1)
        self.assertEqual(out["summary"]["oos_trades"],0)
        self.assertTrue(out["summary"]["missing_pit_windows"])
    def test_reject_zero_cost(self):
        with self.assertRaisesRegex(ValueError,"Positive execution costs"):
            replay(self.bars,self.snap,train_days=5,test_days=4,hold_days=1,
                   buy_fee_pct=0,sell_fee_pct=0,slippage_pct=0)
    def test_reject_duplicate_decisions(self):
        with self.assertRaisesRegex(ValueError,"Duplicate"):
            replay(self.bars,pd.concat([self.snap,self.snap.iloc[:1]]),
                   train_days=5,test_days=4,hold_days=1)
if __name__=="__main__":
    unittest.main()
