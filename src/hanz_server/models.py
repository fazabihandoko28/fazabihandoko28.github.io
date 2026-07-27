from __future__ import annotations
from dataclasses import asdict, dataclass
from enum import IntEnum
from typing import Any, Mapping
class EventPriority(IntEnum): LOW=10; NORMAL=20; HIGH=30; CRITICAL=40
@dataclass(frozen=True)
class DecisionSnapshot:
    symbol:str; market:str; action:str; evidence:int; risk:str; trigger:str|None; price:float|None; updated_at:str; source:str='HANZ'
    @classmethod
    def from_mapping(cls,p:Mapping[str,Any]):
        def f(v):
            try:return None if v in (None,'') else float(v)
            except:return None
        return cls(str(p.get('SIMBOL') or p.get('symbol') or '').strip().upper(),str(p.get('PASAR') or p.get('market') or 'UNKNOWN'),str(p.get('AKSI') or p.get('action') or 'DATA MINIM').strip().upper(),int(p.get('EVIDENCE') or p.get('evidence') or 0),str(p.get('RISIKO') or p.get('risk') or 'BELUM ADA').strip().upper(),p.get('PEMICU') or p.get('trigger'),f(p.get('HARGA') or p.get('price')),str(p.get('updated_at') or p.get('generated_at') or ''),str(p.get('source') or 'HANZ'))
    def to_dict(self): return asdict(self)
@dataclass(frozen=True)
class AlertEvent:
    event_id:str; symbol:str; market:str; event_type:str; old_action:str|None; new_action:str; priority:EventPriority; evidence:int; risk:str; trigger:str|None; price:float|None; created_at:str; message_id:str
    def to_dict(self):
        d=asdict(self); d['priority']=self.priority.name; return d
