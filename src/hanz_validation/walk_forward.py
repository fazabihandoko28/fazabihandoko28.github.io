from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from statistics import fmean
from typing import Iterable

from hanz_core import EntryStatus, decide_entry
from hanz_data import MarketSeries, validate_series
from hanz_technical import build_technical_snapshot


class DecisionOutcome(str, Enum):
    TARGET_FIRST = "TARGET_FIRST"
    STOP_FIRST = "STOP_FIRST"
    TARGET_AND_STOP_SAME_BAR = "TARGET_AND_STOP_SAME_BAR"
    NEITHER = "NEITHER"


@dataclass(frozen=True, slots=True)
class ValidationEvent:
    market: str
    symbol: str
    signal_timestamp: str
    status: str
    entry_close: float
    horizon_bars: int
    target_price: float
    stop_price: float
    outcome: DecisionOutcome
    exit_close: float
    forward_return: float
    max_favorable_excursion: float
    max_adverse_excursion: float
    vetoes: tuple[str, ...]

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["outcome"] = self.outcome.value
        return payload


@dataclass(frozen=True, slots=True)
class ValidationReport:
    market: str
    symbol: str
    evaluated_events: int
    ready_events: int
    wait_events: int
    high_risk_events: int
    reject_events: int
    ready_target_first: int
    ready_stop_first: int
    ready_ambiguous: int
    ready_neither: int
    average_ready_forward_return: float | None
    events: tuple[ValidationEvent, ...]

    def to_dict(self, *, include_events: bool = True) -> dict:
        payload = {
            "market": self.market,
            "symbol": self.symbol,
            "evaluated_events": self.evaluated_events,
            "status_counts": {
                "READY": self.ready_events,
                "WAIT": self.wait_events,
                "HIGH_RISK": self.high_risk_events,
                "REJECT": self.reject_events,
            },
            "ready_outcomes": {
                "TARGET_FIRST": self.ready_target_first,
                "STOP_FIRST": self.ready_stop_first,
                "TARGET_AND_STOP_SAME_BAR": self.ready_ambiguous,
                "NEITHER": self.ready_neither,
            },
            "average_ready_forward_return": self.average_ready_forward_return,
        }
        if include_events:
            payload["events"] = [event.to_dict() for event in self.events]
        return payload


class WalkForwardValidator:
    """Strict no-lookahead validation of the current HANZ decision rules.

    At each historical decision point, the engine receives only bars up to that
    point. Future bars are revealed only after the decision has been recorded.
    The validator measures observed outcomes; it does not claim predictive
    probability or optimize thresholds automatically.
    """

    def __init__(
        self,
        *,
        minimum_bars: int = 60,
        horizon_bars: int = 5,
        step_bars: int = 1,
        target_pct: float = 0.04,
        stop_pct: float = 0.025,
    ) -> None:
        if minimum_bars < 20:
            raise ValueError("minimum_bars must be at least 20")
        if horizon_bars < 1 or step_bars < 1:
            raise ValueError("horizon_bars and step_bars must be positive")
        if target_pct <= 0 or stop_pct <= 0:
            raise ValueError("target_pct and stop_pct must be positive")
        self.minimum_bars = minimum_bars
        self.horizon_bars = horizon_bars
        self.step_bars = step_bars
        self.target_pct = target_pct
        self.stop_pct = stop_pct

    def _classify_path(self, entry: float, future_bars: tuple) -> tuple[DecisionOutcome, float, float]:
        target = entry * (1.0 + self.target_pct)
        stop = entry * (1.0 - self.stop_pct)
        target_index: int | None = None
        stop_index: int | None = None
        for index, bar in enumerate(future_bars):
            if target_index is None and bar.high >= target:
                target_index = index
            if stop_index is None and bar.low <= stop:
                stop_index = index
            if target_index is not None or stop_index is not None:
                if target_index == index and stop_index == index:
                    return DecisionOutcome.TARGET_AND_STOP_SAME_BAR, target, stop
                if target_index == index:
                    return DecisionOutcome.TARGET_FIRST, target, stop
                if stop_index == index:
                    return DecisionOutcome.STOP_FIRST, target, stop
        return DecisionOutcome.NEITHER, target, stop

    def validate(self, series: MarketSeries) -> ValidationReport:
        required = self.minimum_bars + self.horizon_bars
        if len(series.bars) < required:
            raise ValueError(f"insufficient bars for validation: {len(series.bars)}<{required}")

        events: list[ValidationEvent] = []
        last_signal_index = len(series.bars) - self.horizon_bars - 1
        for signal_index in range(self.minimum_bars - 1, last_signal_index + 1, self.step_bars):
            visible = series.bars[: signal_index + 1]
            future = series.bars[signal_index + 1 : signal_index + 1 + self.horizon_bars]
            historical = MarketSeries(symbol=series.symbol, market=series.market, bars=visible)
            report = validate_series(historical, minimum_bars=self.minimum_bars)
            snapshot = build_technical_snapshot(historical, report)
            decision = decide_entry(snapshot.evidence)
            entry = snapshot.close
            outcome, target, stop = self._classify_path(entry, future)
            exit_close = future[-1].close
            forward_return = (exit_close / entry) - 1.0
            max_high = max(bar.high for bar in future)
            min_low = min(bar.low for bar in future)
            mfe = (max_high / entry) - 1.0
            mae = (min_low / entry) - 1.0
            events.append(
                ValidationEvent(
                    market=series.market,
                    symbol=series.symbol,
                    signal_timestamp=snapshot.timestamp.isoformat(),
                    status=decision.status.value,
                    entry_close=entry,
                    horizon_bars=self.horizon_bars,
                    target_price=target,
                    stop_price=stop,
                    outcome=outcome,
                    exit_close=exit_close,
                    forward_return=forward_return,
                    max_favorable_excursion=mfe,
                    max_adverse_excursion=mae,
                    vetoes=tuple(decision.vetoes),
                )
            )

        by_status = {status: 0 for status in EntryStatus}
        for event in events:
            by_status[EntryStatus(event.status)] += 1
        ready = [event for event in events if event.status == EntryStatus.READY.value]
        ready_returns = [event.forward_return for event in ready]
        return ValidationReport(
            market=series.market,
            symbol=series.symbol,
            evaluated_events=len(events),
            ready_events=by_status[EntryStatus.READY],
            wait_events=by_status[EntryStatus.WAIT],
            high_risk_events=by_status[EntryStatus.HIGH_RISK],
            reject_events=by_status[EntryStatus.REJECT],
            ready_target_first=sum(event.outcome is DecisionOutcome.TARGET_FIRST for event in ready),
            ready_stop_first=sum(event.outcome is DecisionOutcome.STOP_FIRST for event in ready),
            ready_ambiguous=sum(event.outcome is DecisionOutcome.TARGET_AND_STOP_SAME_BAR for event in ready),
            ready_neither=sum(event.outcome is DecisionOutcome.NEITHER for event in ready),
            average_ready_forward_return=fmean(ready_returns) if ready_returns else None,
            events=tuple(events),
        )

    def validate_many(self, series_collection: Iterable[MarketSeries]) -> tuple[ValidationReport, ...]:
        return tuple(self.validate(series) for series in series_collection)
