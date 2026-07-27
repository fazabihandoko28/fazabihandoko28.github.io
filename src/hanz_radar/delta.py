from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from hanz_realtime.models import SymbolState


@dataclass(frozen=True)
class DeltaPolicy:
    min_price_change_pct: float = 0.35
    min_anomaly_score: float = 45.0
    min_velocity: float = 0.01
    max_stale_seconds: int = 30


class DeltaScanner:
    def __init__(self, policy: DeltaPolicy | None = None) -> None:
        self.policy = policy or DeltaPolicy()

    def is_interesting(self, state: SymbolState) -> bool:
        if state.last_timestamp is None:
            return False

        return (
            abs(state.price_change_pct) >= self.policy.min_price_change_pct
            or state.anomaly_score >= self.policy.min_anomaly_score
            or abs(state.velocity) >= self.policy.min_velocity
        )

    def is_stale(self, state: SymbolState, now) -> bool:
        if state.last_timestamp is None:
            return True
        return now - state.last_timestamp > timedelta(
            seconds=self.policy.max_stale_seconds
        )
