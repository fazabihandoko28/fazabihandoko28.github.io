from __future__ import annotations

from datetime import datetime
from typing import Iterable

from hanz_realtime.models import SymbolState
from hanz_server.models import DecisionSnapshot

from .engine import OpportunityRadar


class RadarDecisionBridge:
    def __init__(self, radar: OpportunityRadar | None = None) -> None:
        self.radar = radar or OpportunityRadar()

    def decisions(
        self,
        states: Iterable[SymbolState],
        now: datetime | None = None,
    ) -> list[DecisionSnapshot]:
        snapshot = self.radar.evaluate(states, now=now)
        return [
            DecisionSnapshot(
                symbol=signal.symbol,
                market=signal.market,
                action=signal.status.value,
                evidence=signal.evidence,
                risk=signal.risk,
                trigger=signal.trigger,
                price=signal.price,
                updated_at=signal.timestamp.isoformat(),
                source="HANZ_RADAR",
            )
            for signal in snapshot.active_signals
            if signal.status.value != "LEWATI"
        ]
