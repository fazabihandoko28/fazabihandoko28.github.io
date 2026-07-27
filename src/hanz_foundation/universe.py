from dataclasses import dataclass
@dataclass(frozen=True)
class UniverseRecord:
    symbol:str; market:str; active:bool=True; suspended:bool=False; avg_value_traded:float|None=None; avg_volume:float|None=None; data_points:int=0
@dataclass(frozen=True)
class UniverseResult:
    accepted:tuple; rejected:dict
class UniverseBuilder:
    def __init__(self,min_data_points=120,min_avg_value_traded=1_000_000_000.,min_avg_volume=100_000.): self.min_data_points=min_data_points; self.min_avg_value_traded=min_avg_value_traded; self.min_avg_volume=min_avg_volume
    def build(self,records):
        a=[]; r={}
        for x in records:
            q=[]
            if not x.active:q.append('inactive')
            if x.suspended:q.append('suspended')
            if x.data_points<self.min_data_points:q.append('insufficient_history')
            if x.avg_value_traded is None:q.append('missing_value_traded')
            elif x.avg_value_traded<self.min_avg_value_traded:q.append('low_value_traded')
            if x.avg_volume is None:q.append('missing_volume')
            elif x.avg_volume<self.min_avg_volume:q.append('low_volume')
            if q:r[x.symbol]=tuple(q)
            else:a.append(x)
        a.sort(key=lambda z:z.symbol); return UniverseResult(tuple(a),r)
