from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

from hanz_realtime.models import SymbolState

from .delta import DeltaScanner
from .history import RadarHistory
from .models import RadarSignal, RadarSnapshot, RadarStatus


class OpportunityRadar:
    """Convert realtime symbol states into ranked opportunity signals."""

    def __init__(
        self,
        delta: DeltaScanner | None = None,
        history: RadarHistory | None = None,
        max_results: int = 25,
    ) -> None:
        self.delta = delta or DeltaScanner()
        self.history = history or RadarHistory()
        self.max_results = max_results

    def evaluate(
        self,
        states: Iterable[SymbolState],
        now: datetime | None = None,
    ) -> RadarSnapshot:
        now = now or datetime.now(timezone.utc)
        signals: list[RadarSignal] = []
        total = 0

        for state in states:
            total += 1
            if self.delta.is_stale(state, now):
                continue
            if not self.delta.is_interesting(state):
                continue

            signal = self._signal_from_state(state, now)
            signals.append(signal)
            self.history.record(signal)

        signals.sort(
            key=lambda item: (
                self._status_rank(item.status),
                -item.evidence,
                -item.anomaly,
                item.symbol,
            )
        )

        return RadarSnapshot(
            generated_at=now,
            total_symbols=total,
            active_signals=tuple(signals[: self.max_results]),
        )

    def _signal_from_state(
        self,
        state: SymbolState,
        now: datetime,
    ) -> RadarSignal:
        evidence = self._evidence_score(state)
        status = self._status(evidence, state)
        risk = self._risk(state)
        reason = self._reason(state)

        trigger = None
        if status == RadarStatus.PREPARE and state.last_price is not None:
            trigger = f"monitor_above:{state.last_price:g}"

        return RadarSignal(
            symbol=state.symbol,
            market=state.market,
            status=status,
            evidence=evidence,
            anomaly=round(state.anomaly_score, 2),
            risk=risk,
            price=state.last_price,
            trigger=trigger,
            reason=reason,
            timestamp=state.last_timestamp or now,
        )

    @staticmethod
    def _evidence_score(state: SymbolState) -> int:
        score = 0.0
        score += min(abs(state.price_change_pct) * 18.0, 25.0)
        score += min(state.anomaly_score * 0.45, 40.0)
        score += min(abs(state.velocity) * 10.0, 15.0)
        if state.spread_pct is not None:
            score += max(0.0, 15.0 - state.spread_pct * 20.0)
        else:
            score += 5.0
        if state.cumulative_volume > 0:
            score += 5.0
        return int(round(max(0.0, min(score, 100.0))))

    @staticmethod
    def _status(evidence: int, state: SymbolState) -> RadarStatus:
        if evidence >= 82 and state.anomaly_score >= 70:
            return RadarStatus.READY
        if evidence >= 68:
            return RadarStatus.PREPARE
        if evidence >= 52:
            return RadarStatus.EARLY
        return RadarStatus.SKIP

    @staticmethod
    def _risk(state: SymbolState) -> str:
        spread = state.spread_pct
        if spread is None:
            return "BELUM ADA"
        if spread <= 0.35:
            return "RENDAH"
        if spread <= 0.8:
            return "SEDANG"
        return "TINGGI"

    @staticmethod
    def _reason(state: SymbolState) -> str:
        if state.anomaly_score >= 80:
            return "ANOMALI KUAT"
        if state.anomaly_score >= 65:
            return "MOMEN KUAT"
        if abs(state.price_change_pct) >= 1.0:
            return "GERAK CEPAT"
        return "PANTAU"

    @staticmethod
    def _status_rank(status: RadarStatus) -> int:
        order = {
            RadarStatus.READY: 0,
            RadarStatus.PREPARE: 1,
            RadarStatus.EARLY: 2,
            RadarStatus.HOLD: 3,
            RadarStatus.RELEASE: 4,
            RadarStatus.SELL: 5,
            RadarStatus.SKIP: 6,
        }
        return order[status]
