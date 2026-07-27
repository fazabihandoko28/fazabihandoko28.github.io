from dataclasses import dataclass
from .models import EvidenceLevel
from .weighting import AdaptiveWeightEngine
S={EvidenceLevel.STRONG:100.,EvidenceLevel.SUPPORTIVE:78.,EvidenceLevel.NEUTRAL:55.,EvidenceLevel.CAUTION:30.,EvidenceLevel.REJECT:0.,EvidenceLevel.MISSING:0.}
@dataclass(frozen=True)
class ScoreResult:
    score:float; coverage:float; group_scores:dict; profile:object; hard_vetoes:tuple; missing_groups:tuple
class EvidenceScoreEngine:
    def __init__(self, weighting=None): self.w=weighting or AdaptiveWeightEngine()
    def score(self,evidence,regime):
        p=self.w.profile(regime); g=evidence.as_groups(); missing=tuple(k for k,v in g.items() if v==EvidenceLevel.MISSING); veto=tuple(k for k,v in g.items() if k in {'liquidity','risk'} and v==EvidenceLevel.REJECT)
        aw=sum(p.weights[k] for k,v in g.items() if v!=EvidenceLevel.MISSING); cov=round(aw*100,2)
        score=0 if aw<=0 else sum(S[v]*p.weights[k] for k,v in g.items() if v!=EvidenceLevel.MISSING)/aw
        return ScoreResult(round(score,2),cov,{k:S[v] for k,v in g.items()},p,veto,missing)
