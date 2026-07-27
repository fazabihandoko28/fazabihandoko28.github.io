from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping

class MarketRegime(str, Enum):
    BULL_EXPANSION='BULL_EXPANSION'; BULL_WEAKENING='BULL_WEAKENING'; SIDEWAYS='SIDEWAYS'; RECOVERY='RECOVERY'; DISTRIBUTION='DISTRIBUTION'; PANIC='PANIC'; DATA_LIMITED='DATA_LIMITED'
class EvidenceLevel(str, Enum):
    STRONG='STRONG'; SUPPORTIVE='SUPPORTIVE'; NEUTRAL='NEUTRAL'; CAUTION='CAUTION'; REJECT='REJECT'; MISSING='MISSING'
class Action(str, Enum):
    EARLY='EARLY'; PREPARE='PREPARE'; READY='READY'; HOLD='HOLD'; PREPARE_EXIT='PREPARE_EXIT'; EXIT='EXIT'; AVOID='AVOID'; NO_DATA='NO_DATA'
class RiskLevel(str, Enum):
    LOW='LOW'; MEDIUM='MEDIUM'; HIGH='HIGH'; EXTREME='EXTREME'; UNKNOWN='UNKNOWN'

@dataclass(frozen=True)
class EvidenceVector:
    trend: EvidenceLevel=EvidenceLevel.MISSING
    momentum: EvidenceLevel=EvidenceLevel.MISSING
    volume: EvidenceLevel=EvidenceLevel.MISSING
    liquidity: EvidenceLevel=EvidenceLevel.MISSING
    risk: EvidenceLevel=EvidenceLevel.MISSING
    breakout: EvidenceLevel=EvidenceLevel.MISSING
    relative_strength: EvidenceLevel=EvidenceLevel.MISSING
    market: EvidenceLevel=EvidenceLevel.MISSING
    raw_metrics: Mapping[str,float|int|str|None]=field(default_factory=dict)
    def as_groups(self):
        return {'trend':self.trend,'momentum':self.momentum,'volume':self.volume,'liquidity':self.liquidity,'risk':self.risk,'breakout':self.breakout,'relative_strength':self.relative_strength,'market':self.market}

@dataclass(frozen=True)
class StockSnapshot:
    symbol:str; market:str; regime:MarketRegime; evidence:EvidenceVector
    price:float|None=None; resistance:float|None=None; support:float|None=None; is_held:bool=False
