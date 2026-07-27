from dataclasses import dataclass
from .models import Action,EvidenceLevel,RiskLevel
from .scoring import EvidenceScoreEngine
@dataclass(frozen=True)
class DecisionResult:
    symbol:str; action:Action; score:float; coverage:float; risk:RiskLevel; passed:tuple; warnings:tuple; vetoes:tuple; missing:tuple; next_trigger:str|None
class DecisionEngine:
    def __init__(self, scoring=None): self.s=scoring or EvidenceScoreEngine()
    def decide(self,x):
        r=self.s.score(x.evidence,x.regime); g=x.evidence.as_groups(); passed=tuple(k for k,v in g.items() if v in {EvidenceLevel.STRONG,EvidenceLevel.SUPPORTIVE}); warnings=tuple(k for k,v in g.items() if v in {EvidenceLevel.CAUTION,EvidenceLevel.NEUTRAL})
        risk={EvidenceLevel.STRONG:RiskLevel.LOW,EvidenceLevel.SUPPORTIVE:RiskLevel.MEDIUM,EvidenceLevel.CAUTION:RiskLevel.HIGH,EvidenceLevel.REJECT:RiskLevel.HIGH}.get(g.get('risk'),RiskLevel.UNKNOWN)
        if r.coverage<65: a=Action.NO_DATA
        elif r.hard_vetoes: a=Action.AVOID
        elif x.is_held:
            if r.hard_vetoes or g.get('trend')==EvidenceLevel.REJECT: a=Action.EXIT
            elif r.score<r.profile.early_threshold or g.get('momentum')==EvidenceLevel.CAUTION or g.get('volume')==EvidenceLevel.CAUTION: a=Action.PREPARE_EXIT
            else: a=Action.HOLD
        elif r.score>=r.profile.ready_threshold: a=Action.READY
        elif r.score>=r.profile.prepare_threshold: a=Action.PREPARE
        elif r.score>=r.profile.early_threshold: a=Action.EARLY
        else: a=Action.AVOID
        trigger=(f'close_above:{x.resistance:g}' if a==Action.PREPARE and x.resistance is not None else 'volume_and_strength_confirmation' if a==Action.EARLY else 'execution_plan' if a==Action.READY else None)
        return DecisionResult(x.symbol,a,r.score,r.coverage,risk,passed,warnings,r.hard_vetoes,r.missing_groups,trigger)
