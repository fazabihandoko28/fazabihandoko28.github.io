from __future__ import annotations

from dataclasses import dataclass
from typing import Any


EVIDENCE_WEIGHTS: dict[str, int] = {
    "data_freshness": 14,
    "liquidity": 14,
    "risk_reward": 16,
    "market_regime": 12,
    "price_structure": 14,
    "resistance": 12,
    "volume_confirmation": 10,
    "extension_risk": 8,
}

SIGNAL_MULTIPLIER: dict[str, float] = {
    "positive": 1.0,
    "neutral": 0.55,
    "warning": 0.2,
    "negative": 0.0,
    "unknown": 0.1,
}


@dataclass(frozen=True, slots=True)
class TradePlan:
    entry_low: float | None
    entry_high: float | None
    stop: float | None
    target_1: float | None
    target_2: float | None
    reward_risk_1: float | None
    reward_risk_2: float | None
    valid: bool
    note: str


def evidence_quality(item: dict[str, Any]) -> int:
    """Return an evidence-quality index, not a success probability."""
    evidence = item.get("evidence") or {}
    signal_by_name: dict[str, str] = {}
    for bucket in ("positive", "neutral", "warning", "negative", "unknown"):
        for name in evidence.get(bucket) or []:
            signal_by_name[str(name)] = bucket

    earned = 0.0
    total = float(sum(EVIDENCE_WEIGHTS.values()))
    for name, weight in EVIDENCE_WEIGHTS.items():
        earned += weight * SIGNAL_MULTIPLIER.get(signal_by_name.get(name, "unknown"), 0.1)

    status = str(item.get("entry_status", "WAIT"))
    status_adjustment = {"READY": 8, "WAIT": 0, "HIGH_RISK": -14, "REJECT": -24}.get(status, 0)
    veto_penalty = min(20, 6 * len(item.get("vetoes") or []))
    score = round((earned / total) * 100 + status_adjustment - veto_penalty)
    return max(0, min(100, score))


def quality_grade(score: int, status: str) -> str:
    if status == "REJECT":
        return "REJECTED"
    if score >= 92:
        return "AAA"
    if score >= 84:
        return "AA"
    if score >= 74:
        return "A"
    if score >= 62:
        return "BBB"
    if score >= 50:
        return "BB"
    return "WATCH"


def trade_plan(item: dict[str, Any]) -> TradePlan:
    technical = item.get("technical") or {}
    close = _number(item.get("signal_close"))
    atr = _number(technical.get("atr14"))
    support = _number(technical.get("support20"))
    resistance = _number(technical.get("resistance20"))
    status = str(item.get("entry_status", "WAIT"))

    if close is None or close <= 0 or atr is None or atr <= 0:
        return TradePlan(None, None, None, None, None, None, None, False, "Insufficient price or ATR data")

    entry_low = max(0.0, close - 0.25 * atr)
    entry_high = close + 0.15 * atr
    stop_atr = close - 1.5 * atr
    stop = max(stop_atr, support * 0.995) if support and support > 0 else stop_atr
    if stop >= entry_low:
        stop = close - 1.25 * atr

    risk = max(entry_high - stop, 0.01)
    target_1 = close + 2.0 * risk
    target_2 = close + 3.0 * risk
    if resistance and resistance > entry_high:
        target_1 = max(target_1, resistance)
        target_2 = max(target_2, resistance + risk)

    rr1 = (target_1 - entry_high) / risk
    rr2 = (target_2 - entry_high) / risk
    valid = status == "READY" and rr1 >= 1.8
    note = "Research plan only; confirm liquidity and live price before any decision."
    if status != "READY":
        note = "Watchlist plan only; wait for READY evidence before considering entry."
    return TradePlan(entry_low, entry_high, stop, target_1, target_2, rr1, rr2, valid, note)


def market_health(market: dict[str, Any]) -> dict[str, Any]:
    universe = int(market.get("universe_size") or 0)
    errors = int(market.get("error_count") or 0)
    candidates = market.get("candidates") or []
    reviewed = market.get("reviewed") or []
    rejected = int(market.get("rejected_count") or 0)
    analyzed = max(0, universe - errors)
    ready = sum(1 for item in candidates if str(item.get("entry_status")) == "READY")
    developing = len(candidates) + len(reviewed)

    coverage = analyzed / universe if universe else 0.0
    breadth = developing / analyzed if analyzed else 0.0
    reject_ratio = rejected / analyzed if analyzed else 1.0
    health_score = round(55 * coverage + 30 * min(1.0, breadth * 4) + 15 * (1 - min(1.0, reject_ratio)))
    health_score = max(0, min(100, health_score))

    if coverage < 0.8:
        label = "DATA LIMITED"
        exposure = 0
        explanation = "Coverage is too low for a reliable market view."
    elif ready >= 3 and health_score >= 70:
        label = "CONSTRUCTIVE"
        exposure = 60
        explanation = "Several setups show aligned evidence, but position sizing must remain controlled."
    elif ready >= 1 or developing >= 3:
        label = "SELECTIVE"
        exposure = 35
        explanation = "Some evidence is developing; favor patience and smaller paper positions."
    else:
        label = "DEFENSIVE"
        exposure = 10
        explanation = "Few setups meet the evidence standard; capital preservation dominates."

    return {
        "label": label,
        "score": health_score,
        "paper_exposure_percent": exposure,
        "explanation": explanation,
    }


def explain_no_candidate(market: dict[str, Any]) -> list[str]:
    if market.get("candidates"):
        return []
    reviewed = market.get("reviewed") or []
    rejected = market.get("rejected") or []
    errors = market.get("errors") or []
    reasons: list[str] = []
    if errors:
        reasons.append(f"{len(errors)} symbols could not be analyzed because of data errors.")
    warning_counts: dict[str, int] = {}
    negative_counts: dict[str, int] = {}
    for item in [*reviewed, *rejected]:
        evidence = item.get("evidence") or {}
        for name in evidence.get("warning") or []:
            warning_counts[name] = warning_counts.get(name, 0) + 1
        for name in evidence.get("negative") or []:
            negative_counts[name] = negative_counts.get(name, 0) + 1
    combined = sorted(
        [(count, name, "warning") for name, count in warning_counts.items()]
        + [(count, name, "negative") for name, count in negative_counts.items()],
        reverse=True,
    )
    for count, name, kind in combined[:3]:
        reasons.append(f"{count} setups had {kind} evidence in {name.replace('_', ' ')}.")
    if not reasons:
        reasons.append("No setup achieved sufficient evidence alignment for READY status.")
    return reasons


def _number(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None
