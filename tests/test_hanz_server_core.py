import tempfile,unittest
from pathlib import Path
from hanz_server import DecisionSnapshot,EventEngine,EventPolicy,HanzRealtimeService,SQLiteStateStore
class N:
 def __init__(self):self.events=[]
 def send(self,e):self.events.append(e);return True
class T(unittest.TestCase):
 def s(self,a='AWAL',e=60,r='SEDANG'):return DecisionSnapshot('TINS','BEI',a,e,r,'close_above:3780',3440.0,'2026-07-27T13:42:43+00:00')
 def test_new(self):self.assertIsNotNone(EventEngine(EventPolicy(cooldown_seconds=0)).evaluate(None,self.s()))
 def test_upgrade(self):
  x=EventEngine(EventPolicy(cooldown_seconds=0)).evaluate(self.s('AWAL',60),self.s('EKSEKUSI',82));self.assertEqual(x.event_type,'UPGRADE');self.assertEqual(x.priority.name,'HIGH')
 def test_duplicate(self):
  e=EventEngine(EventPolicy(cooldown_seconds=0));self.assertIsNotNone(e.evaluate(None,self.s('SIAGA',70)));self.assertIsNone(e.evaluate(None,self.s('SIAGA',70)))
 def test_low(self):self.assertIsNone(EventEngine(EventPolicy(min_evidence=55,cooldown_seconds=0)).evaluate(None,self.s('AWAL',40)))
 def test_store(self):
  with tempfile.TemporaryDirectory() as d:
   st=SQLiteStateStore(Path(d)/'x.db');s=self.s();st.upsert_decision(s);self.assertEqual(st.get_decision('BEI','TINS'),s)
 def test_service(self):
  with tempfile.TemporaryDirectory() as d:
   n=N();sv=HanzRealtimeService(SQLiteStateStore(Path(d)/'x.db'),EventEngine(EventPolicy(cooldown_seconds=0)),[n]);self.assertIsNotNone(sv.process_decision(self.s('SIAGA',70)));self.assertEqual(len(n.events),1)
 def test_payload(self):
  with tempfile.TemporaryDirectory() as d:
   sv=HanzRealtimeService(SQLiteStateStore(Path(d)/'x.db'),EventEngine(EventPolicy(cooldown_seconds=0)),[N()]);p={'markets':[{'PASAR':'BEI','KEPUTUSAN':[{'SIMBOL':'TINS','AKSI':'SIAGA','EVIDENCE':72,'RISIKO':'SEDANG','PEMICU':'close_above:3780'}]}]};self.assertEqual(len(sv.process_payload(p)),1)
if __name__=='__main__':unittest.main()
