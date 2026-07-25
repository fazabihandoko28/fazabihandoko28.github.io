from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class SourceGrade(str, Enum):
    OFFICIAL = "OFFICIAL"
    LICENSED = "LICENSED"
    RESEARCH = "RESEARCH"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class SourcePolicy:
    name: str
    grade: SourceGrade
    allowed_for_paper_trade: bool
    allowed_for_live_trade: bool
    delayed: bool
    notes: str


SOURCE_POLICIES: dict[str, SourcePolicy] = {
    "YAHOO_FINANCE_RESEARCH_ONLY": SourcePolicy(
        name="YAHOO_FINANCE_RESEARCH_ONLY",
        grade=SourceGrade.RESEARCH,
        allowed_for_paper_trade=True,
        allowed_for_live_trade=False,
        delayed=True,
        notes="Public research source. Coverage and timeliness must be independently checked.",
    ),
    "CSV": SourcePolicy(
        name="CSV",
        grade=SourceGrade.UNKNOWN,
        allowed_for_paper_trade=True,
        allowed_for_live_trade=False,
        delayed=True,
        notes="Trust depends on the provenance of the imported file.",
    ),
}


def require_paper_trade_source(source_name: str) -> SourcePolicy:
    policy = SOURCE_POLICIES.get(source_name)
    if policy is None or not policy.allowed_for_paper_trade:
        raise ValueError(f"Source is not approved for paper trading: {source_name}")
    return policy


def require_live_trade_source(source_name: str) -> SourcePolicy:
    policy = SOURCE_POLICIES.get(source_name)
    if policy is None or not policy.allowed_for_live_trade:
        raise ValueError(f"Source is not approved for live trading: {source_name}")
    return policy
