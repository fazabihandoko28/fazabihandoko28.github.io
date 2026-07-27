import unittest
from hanz_foundation import *
def ev(**o):
    x=dict(trend=EvidenceLevel.STRONG,momentum=EvidenceLevel.SUPPORTIVE,volume=EvidenceLevel.STRONG,liquidity=EvidenceLevel.STRONG,risk=EvidenceLevel.SUPPORTIVE,breakout=EvidenceLevel.SUPPORTIVE,relative_strength=EvidenceLevel.STRONG,market=EvidenceLevel.SUPPORTIVE); x.update(o); return EvidenceVector(**x)
class T(unittest.TestCase):
    def test_ready(self):
        d=DecisionEngine().decide(StockSnapshot('TEST','BEI',MarketRegime.BULL_EXPANSION,ev(),100,101)); self.assertEqual(d.action,Action.READY)
    def test_veto(self):
        d=DecisionEngine().decide(StockSnapshot('BAD','BEI',MarketRegime.BULL_EXPANSION,ev(liquidity=EvidenceLevel.REJECT))); self.assertEqual(d.action,Action.AVOID)
    def test_missing(self):
        d=DecisionEngine().decide(StockSnapshot('MISS','BEI',MarketRegime.BULL_EXPANSION,EvidenceVector(trend=EvidenceLevel.STRONG))); self.assertEqual(d.action,Action.NO_DATA)
    def test_exit(self):
        d=DecisionEngine().decide(StockSnapshot('HELD','BEI',MarketRegime.DISTRIBUTION,ev(trend=EvidenceLevel.REJECT,risk=EvidenceLevel.CAUTION),is_held=True)); self.assertEqual(d.action,Action.EXIT)
    def test_ui(self):
        d=DecisionEngine().decide(StockSnapshot('ID','BEI',MarketRegime.BULL_EXPANSION,ev())); u=ExplainEngine().compact_id(d); self.assertEqual(u['AKSI'],'EKSEKUSI'); self.assertLessEqual(len(u['AKSI'].split()),2)
    def test_universe(self):
        r=UniverseBuilder().build([UniverseRecord('AAA','BEI',avg_value_traded=2e9,avg_volume=5e5,data_points=200),UniverseRecord('BBB','BEI',suspended=True,avg_value_traded=2e9,avg_volume=5e5,data_points=200)]); self.assertEqual([x.symbol for x in r.accepted],['AAA']); self.assertIn('BBB',r.rejected)
    def test_deterministic(self):
        e=EvidenceScoreEngine(); self.assertEqual(e.score(ev(),MarketRegime.SIDEWAYS),e.score(ev(),MarketRegime.SIDEWAYS))
if __name__=='__main__':unittest.main()
