from __future__ import annotations
from typing import Iterable
from .models import Decision, EntryStatus, Evidence, Signal

HARD_VETO_NAMES = {
    "data_freshness",
    "liquidity",
    "spread",
    "support_invalidation",
    "suspension",
    "extension_risk",
    "risk_reward",
    "official_disclosure_conflict",
}

CORE_REQUIRED = {
    "data_freshness",
    "liquidity",
    "market_regime",
    "price_structure",
    "volume_confirmation",
    "resistance",
    "risk_reward",
}


def decide_entry(evidence: Iterable[Evidence]) -> Decision:
    items = list(evidence)
    by_name = {e.name: e for e in items}
    audit = {e.name: f"{e.signal.value}|{e.source}|{e.timestamp}|{e.detail}" for e in items}

    missing = sorted(name for name in CORE_REQUIRED if name not in by_name)
    if missing:
        return Decision(
            status=EntryStatus.WAIT,
            reasons=["Critical evidence is incomplete"],
            vetoes=[],
            audit={**audit, "missing": ",".join(missing)},
        )

    vetoes = []
    for e in items:
        if e.name in HARD_VETO_NAMES and e.signal == Signal.NEGATIVE:
            vetoes.append(e.name)
        if e.critical and e.signal == Signal.UNKNOWN:
            vetoes.append(f"{e.name}:unknown")

    if vetoes:
        return Decision(
            status=EntryStatus.REJECT,
            reasons=["Hard disqualifier active"],
            vetoes=sorted(vetoes),
            audit=audit,
        )

    positives = sum(e.signal == Signal.POSITIVE for e in items)
    warnings = sum(e.signal == Signal.WARNING for e in items)
    negatives = sum(e.signal == Signal.NEGATIVE for e in items)
    unknowns = sum(e.signal == Signal.UNKNOWN for e in items)

    contradiction = positives >= 3 and (warnings + negatives) >= 2
    if contradiction:
        return Decision(
            status=EntryStatus.WAIT,
            reasons=["Conflicting evidence requires confirmation"],
            audit=audit,
        )

    if negatives > 0 or warnings >= 3:
        return Decision(
            status=EntryStatus.HIGH_RISK,
            reasons=["Setup exists but risk evidence is elevated"],
            audit=audit,
        )

    if unknowns > 1:
        return Decision(
            status=EntryStatus.WAIT,
            reasons=["Too much unresolved evidence"],
            audit=audit,
        )

    mandatory_positive = all(
        by_name[name].signal == Signal.POSITIVE
        for name in ("data_freshness", "liquidity", "price_structure", "volume_confirmation", "risk_reward")
    )
    resistance_ok = by_name["resistance"].signal in {Signal.POSITIVE, Signal.NEUTRAL}
    regime_ok = by_name["market_regime"].signal in {Signal.POSITIVE, Signal.NEUTRAL}

    if mandatory_positive and resistance_ok and regime_ok and positives >= 5:
        return Decision(
            status=EntryStatus.READY,
            reasons=["Required evidence aligned and no hard veto detected"],
            audit=audit,
        )

    return Decision(
        status=EntryStatus.WAIT,
        reasons=["Evidence is not yet mature enough"],
        audit=audit,
    )
