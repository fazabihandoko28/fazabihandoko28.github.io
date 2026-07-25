from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, Mapping

from hanz_core import Decision, EntryStatus, Evidence, Signal, decide_entry
from hanz_data import MarketDataProvider, validate_series
from hanz_technical import TechnicalSnapshot, build_technical_snapshot


class CandidateTier(str, Enum):
    """Evidence-quality tier; deliberately not a probability or prediction."""

    PRIMARY = "PRIMARY"
    SECONDARY = "SECONDARY"
    OBSERVE = "OBSERVE"
    DISQUALIFIED = "DISQUALIFIED"
    DATA_ERROR = "DATA_ERROR"


@dataclass(frozen=True, slots=True)
class EvidenceSummary:
    positive: tuple[str, ...] = ()
    neutral: tuple[str, ...] = ()
    warning: tuple[str, ...] = ()
    negative: tuple[str, ...] = ()
    unknown: tuple[str, ...] = ()

    @classmethod
    def from_evidence(cls, evidence: Iterable[Evidence]) -> "EvidenceSummary":
        buckets: dict[Signal, list[str]] = {signal: [] for signal in Signal}
        for item in evidence:
            buckets[item.signal].append(item.name)
        return cls(
            positive=tuple(sorted(buckets[Signal.POSITIVE])),
            neutral=tuple(sorted(buckets[Signal.NEUTRAL])),
            warning=tuple(sorted(buckets[Signal.WARNING])),
            negative=tuple(sorted(buckets[Signal.NEGATIVE])),
            unknown=tuple(sorted(buckets[Signal.UNKNOWN])),
        )


@dataclass(frozen=True, slots=True)
class ScanResult:
    symbol: str
    market: str
    decision: Decision
    tier: CandidateTier
    snapshot: TechnicalSnapshot | None
    evidence: EvidenceSummary = field(default_factory=EvidenceSummary)
    selection_reasons: tuple[str, ...] = ()
    rejection_reasons: tuple[str, ...] = ()
    error: str | None = None


@dataclass(frozen=True, slots=True)
class MarketScanReport:
    market: str
    candidates: tuple[ScanResult, ...]
    reviewed: tuple[ScanResult, ...]
    rejected: tuple[ScanResult, ...]
    errors: tuple[ScanResult, ...]
    universe_size: int


class MarketScanner:
    """Autonomous evidence-first scanner.

    It discovers symbols, validates every series, isolates symbol failures, applies
    the Core Decision Engine, and returns only a bounded candidate list. Ranking is
    deterministic and based on evidence dominance—not a claimed success probability.
    """

    _status_order: Mapping[EntryStatus, int] = {
        EntryStatus.READY: 0,
        EntryStatus.WAIT: 1,
        EntryStatus.HIGH_RISK: 2,
        EntryStatus.REJECT: 3,
    }

    _evidence_importance: Mapping[str, int] = {
        "data_freshness": 100,
        "liquidity": 95,
        "risk_reward": 90,
        "market_regime": 85,
        "price_structure": 80,
        "resistance": 75,
        "volume_confirmation": 70,
        "extension_risk": 65,
    }

    def __init__(
        self,
        provider: MarketDataProvider,
        *,
        minimum_bars: int = 60,
        candidate_limit: int = 5,
    ) -> None:
        if minimum_bars < 1:
            raise ValueError("minimum_bars must be positive")
        if candidate_limit < 1:
            raise ValueError("candidate_limit must be positive")
        self.provider = provider
        self.minimum_bars = minimum_bars
        self.candidate_limit = candidate_limit

    def _tier(self, decision: Decision, summary: EvidenceSummary) -> CandidateTier:
        if decision.status is EntryStatus.REJECT:
            return CandidateTier.DISQUALIFIED
        if decision.status is EntryStatus.READY and not summary.warning and not summary.negative:
            return CandidateTier.PRIMARY
        if decision.status in {EntryStatus.READY, EntryStatus.WAIT} and not summary.negative:
            return CandidateTier.SECONDARY
        return CandidateTier.OBSERVE

    def _dominance_key(self, result: ScanResult) -> tuple:
        """Sort strongest evidence first without presenting a public score.

        The tuple is lexicographic: hard status, then high-importance negative and
        warning evidence, unresolved evidence, high-importance positives, proximity
        safeguards, and finally stable market/symbol ordering.
        """
        evidence_by_name = {
            item.name: item.signal for item in (result.snapshot.evidence if result.snapshot else ())
        }
        weighted_negative = sum(
            self._evidence_importance.get(name, 50)
            for name, signal in evidence_by_name.items()
            if signal is Signal.NEGATIVE
        )
        weighted_warning = sum(
            self._evidence_importance.get(name, 50)
            for name, signal in evidence_by_name.items()
            if signal is Signal.WARNING
        )
        weighted_unknown = sum(
            self._evidence_importance.get(name, 50)
            for name, signal in evidence_by_name.items()
            if signal is Signal.UNKNOWN
        )
        weighted_positive = sum(
            self._evidence_importance.get(name, 50)
            for name, signal in evidence_by_name.items()
            if signal is Signal.POSITIVE
        )
        rvol = result.snapshot.relative_volume20 if result.snapshot and result.snapshot.relative_volume20 else 0.0
        return (
            self._status_order[result.decision.status],
            weighted_negative,
            weighted_warning,
            weighted_unknown,
            -weighted_positive,
            -rvol,
            result.market,
            result.symbol,
        )

    @staticmethod
    def _explain(decision: Decision, summary: EvidenceSummary) -> tuple[tuple[str, ...], tuple[str, ...]]:
        selected: list[str] = []
        rejected: list[str] = []
        if decision.status is EntryStatus.READY:
            selected.append("Core evidence aligned with no active hard veto")
        elif decision.status is EntryStatus.WAIT:
            selected.append("Evidence retained for confirmation")
        elif decision.status is EntryStatus.HIGH_RISK:
            rejected.append("Risk evidence is elevated")
        else:
            rejected.append("Hard disqualifier active")
        selected.extend(f"Positive: {name}" for name in summary.positive)
        rejected.extend(f"Negative: {name}" for name in summary.negative)
        rejected.extend(f"Warning: {name}" for name in summary.warning)
        rejected.extend(f"Unknown: {name}" for name in summary.unknown)
        rejected.extend(f"Veto: {name}" for name in decision.vetoes)
        return tuple(selected), tuple(rejected)

    def _scan_symbol(self, market: str, symbol: str) -> ScanResult:
        try:
            series = self.provider.load_series(market, symbol)
            report = validate_series(series, minimum_bars=self.minimum_bars)
            snapshot = build_technical_snapshot(series, report)
            decision = decide_entry(snapshot.evidence)
            summary = EvidenceSummary.from_evidence(snapshot.evidence)
            selected, rejected = self._explain(decision, summary)
            return ScanResult(
                symbol=symbol,
                market=market.upper(),
                decision=decision,
                tier=self._tier(decision, summary),
                snapshot=snapshot,
                evidence=summary,
                selection_reasons=selected,
                rejection_reasons=rejected,
            )
        except Exception as exc:  # one malformed symbol never stops a market scan
            decision = Decision(
                status=EntryStatus.WAIT,
                reasons=["Data processing failed"],
                audit={"error": str(exc)},
            )
            return ScanResult(
                symbol=symbol,
                market=market.upper(),
                decision=decision,
                tier=CandidateTier.DATA_ERROR,
                snapshot=None,
                rejection_reasons=("Data processing failed",),
                error=str(exc),
            )

    def scan_market(self, market: str) -> MarketScanReport:
        symbols = tuple(sorted(set(self.provider.list_symbols(market))))
        all_results = tuple(self._scan_symbol(market, symbol) for symbol in symbols)
        ranked = tuple(sorted(all_results, key=self._dominance_key))
        eligible = tuple(
            item for item in ranked
            if item.tier in {CandidateTier.PRIMARY, CandidateTier.SECONDARY}
        )
        candidates = eligible[: self.candidate_limit]
        candidate_ids = {(item.market, item.symbol) for item in candidates}
        reviewed = tuple(
            item for item in ranked
            if item.error is None
            and item.tier is not CandidateTier.DISQUALIFIED
            and (item.market, item.symbol) not in candidate_ids
        )
        rejected = tuple(item for item in ranked if item.tier is CandidateTier.DISQUALIFIED)
        errors = tuple(item for item in ranked if item.error is not None)
        return MarketScanReport(
            market=market.upper(),
            candidates=candidates,
            reviewed=reviewed,
            rejected=rejected,
            errors=errors,
            universe_size=len(symbols),
        )

    def scan_markets(self, markets: Iterable[str]) -> tuple[MarketScanReport, ...]:
        return tuple(self.scan_market(market) for market in markets)
