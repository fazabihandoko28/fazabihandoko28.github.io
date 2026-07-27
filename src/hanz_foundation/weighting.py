from dataclasses import dataclass
from .models import MarketRegime
@dataclass(frozen=True)
class WeightProfile:
    weights:dict[str,float]; ready_threshold:float; prepare_threshold:float; early_threshold:float
class AdaptiveWeightEngine:
    _BASE={'trend':.18,'momentum':.13,'volume':.15,'liquidity':.13,'risk':.15,'breakout':.11,'relative_strength':.10,'market':.05}
    def profile(self, regime):
        w=dict(self._BASE)
        if regime==MarketRegime.BULL_EXPANSION:
            w['momentum']+=.03; w['relative_strength']+=.02; w['risk']-=.03; w['liquidity']-=.02; t=(72,61,51)
        elif regime==MarketRegime.RECOVERY:
            w['trend']+=.03; w['volume']+=.02; w['breakout']+=.02; w['momentum']-=.02; w['market']-=.02; w['relative_strength']-=.03; t=(76,64,53)
        elif regime==MarketRegime.SIDEWAYS:
            w['breakout']+=.04; w['risk']+=.03; w['momentum']-=.03; w['market']-=.04; t=(80,68,57)
        elif regime in {MarketRegime.BULL_WEAKENING,MarketRegime.DISTRIBUTION}:
            w['risk']+=.05; w['liquidity']+=.02; w['market']+=.02; w['momentum']-=.03; w['breakout']-=.03; w['relative_strength']-=.03; t=(84,72,61)
        elif regime==MarketRegime.PANIC:
            w['risk']+=.10; w['liquidity']+=.05; w['trend']-=.05; w['momentum']-=.04; w['breakout']-=.04; w['relative_strength']-=.02; t=(90,80,70)
        else: t=(88,78,68)
        total=sum(w.values()); w={k:v/total for k,v in w.items()}
        return WeightProfile(w,*t)
