from dataclasses import dataclass
from datetime import datetime,timedelta,timezone
from hashlib import sha256
from .models import AlertEvent,DecisionSnapshot,EventPriority
R={'DATA MINIM':0,'LEWATI':1,'AWAL':2,'SIAGA':3,'EKSEKUSI':4,'TAHAN':4,'LEPAS':2,'JUAL':0}
@dataclass(frozen=True)
class EventPolicy:
    min_evidence:int=55; min_evidence_delta:int=8; cooldown_seconds:int=300; notify_actions:tuple=('AWAL','SIAGA','EKSEKUSI','LEPAS','JUAL')
class EventEngine:
    def __init__(self,policy=None): self.policy=policy or EventPolicy(); self.last_at={}; self.last_id={}
    def evaluate(self,previous,current,now=None):
        now=now or datetime.now(timezone.utc)
        if not current.symbol or current.action not in self.policy.notify_actions:return None
        if current.evidence<self.policy.min_evidence and current.action not in {'LEPAS','JUAL'}:return None
        changed=previous is None or previous.action!=current.action
        delta=current.evidence if previous is None else abs(current.evidence-previous.evidence)
        risk_changed=previous is not None and previous.risk!=current.risk
        trigger_changed=previous is not None and previous.trigger!=current.trigger
        if not changed and delta<self.policy.min_evidence_delta and not risk_changed and not trigger_changed:return None
        old=previous.action if previous else 'NONE'; raw=f'{current.market}|{current.symbol}|{old}|{current.action}|{current.evidence}|{current.risk}|{current.trigger}|{current.price}'; mid=sha256(raw.encode()).hexdigest()[:20]; key=f'{current.market}:{current.symbol}'
        if self.last_id.get(key)==mid:return None
        if key in self.last_at and now-self.last_at[key]<timedelta(seconds=self.policy.cooldown_seconds) and current.action not in {'EKSEKUSI','JUAL'}:return None
        et='NEW_SIGNAL' if previous is None else ('UPGRADE' if R.get(current.action,0)>R.get(previous.action,0) else 'DOWNGRADE' if R.get(current.action,0)<R.get(previous.action,0) else 'RISK_CHANGE' if risk_changed else 'TRIGGER_CHANGE' if trigger_changed else 'EVIDENCE_CHANGE')
        pr=EventPriority.CRITICAL if current.action=='JUAL' else EventPriority.HIGH if current.action in {'EKSEKUSI','LEPAS'} else EventPriority.NORMAL if current.action=='SIAGA' else EventPriority.LOW
        eid=sha256(f'{key}|{mid}|{now.isoformat()}'.encode()).hexdigest()[:24]
        e=AlertEvent(eid,current.symbol,current.market,et,None if previous is None else previous.action,current.action,pr,current.evidence,current.risk,current.trigger,current.price,now.isoformat(),mid)
        self.last_id[key]=mid; self.last_at[key]=now; return e
