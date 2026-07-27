import json
from pathlib import Path
from .models import DecisionSnapshot
from .event_engine import EventEngine
from .notifier import ConsoleNotifier
class HanzRealtimeService:
    def __init__(self,store,engine=None,notifiers=None): self.store=store; self.engine=engine or EventEngine(); self.notifiers=list(notifiers or [ConsoleNotifier()])
    def process_decision(self,d):
        prev=self.store.get_decision(d.market,d.symbol); e=self.engine.evaluate(prev,d); self.store.upsert_decision(d)
        if e is None:return None
        self.store.save_event(e); delivered=False
        for n in self.notifiers: delivered=n.send(e) or delivered
        if delivered:self.store.mark_delivered(e.event_id)
        return e
    def process_payload(self,p):
        out=[]
        for m in p.get('markets',[]):
            market=str(m.get('PASAR') or m.get('market') or 'UNKNOWN')
            for item in m.get('KEPUTUSAN') or m.get('decisions') or []:
                x=dict(item); x.setdefault('PASAR',market); x.setdefault('generated_at',p.get('generated_at')); e=self.process_decision(DecisionSnapshot.from_mapping(x));
                if e is not None: out.append(e)
        return out
    def process_file(self,path):return self.process_payload(json.loads(Path(path).read_text(encoding='utf-8')))
