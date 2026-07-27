from __future__ import annotations
import json, sqlite3
from pathlib import Path
from .models import DecisionSnapshot, AlertEvent, EventPriority
class SQLiteStateStore:
    def __init__(self,path='data/hanz_realtime.db'):
        self.path=Path(path); self.path.parent.mkdir(parents=True,exist_ok=True); self._init()
    def _con(self): c=sqlite3.connect(self.path); c.row_factory=sqlite3.Row; return c
    def _init(self):
        with self._con() as c:
            c.executescript("CREATE TABLE IF NOT EXISTS decisions(market TEXT,symbol TEXT,payload TEXT,updated_at TEXT,PRIMARY KEY(market,symbol));CREATE TABLE IF NOT EXISTS events(event_id TEXT PRIMARY KEY,payload TEXT,created_at TEXT,delivered INTEGER DEFAULT 0);")
    def get_decision(self,market,symbol):
        with self._con() as c:r=c.execute('SELECT payload FROM decisions WHERE market=? AND symbol=?',(market,symbol)).fetchone()
        return None if r is None else DecisionSnapshot.from_mapping(json.loads(r['payload']))
    def upsert_decision(self,d):
        with self._con() as c:c.execute('INSERT INTO decisions VALUES(?,?,?,?) ON CONFLICT(market,symbol) DO UPDATE SET payload=excluded.payload,updated_at=excluded.updated_at',(d.market,d.symbol,json.dumps(d.to_dict(),ensure_ascii=False),d.updated_at))
    def save_event(self,e):
        with self._con() as c:c.execute('INSERT OR IGNORE INTO events VALUES(?,?,?,0)',(e.event_id,json.dumps(e.to_dict(),ensure_ascii=False),e.created_at))
    def list_events(self,limit=50):
        with self._con() as c:rows=c.execute('SELECT payload FROM events ORDER BY created_at DESC LIMIT ?',(max(1,min(limit,500)),)).fetchall()
        out=[]
        for r in rows:
            p=json.loads(r['payload']); out.append(AlertEvent(p['event_id'],p['symbol'],p['market'],p['event_type'],p.get('old_action'),p['new_action'],EventPriority[p['priority']],int(p['evidence']),p['risk'],p.get('trigger'),p.get('price'),p['created_at'],p['message_id']))
        return out
    def mark_delivered(self,event_id):
        with self._con() as c:c.execute('UPDATE events SET delivered=1 WHERE event_id=?',(event_id,))
