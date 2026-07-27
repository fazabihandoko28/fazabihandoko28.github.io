from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Iterable, Mapping

from hanz_foundation import (
    DecisionEngine,
    EvidenceLevel,
    EvidenceVector,
    ExplainEngine,
    MarketRegime,
    StockSnapshot,
)


def _norm(value: Any) -> str:
    return str(value or "").strip().upper().replace(" ", "_").replace("-", "_")


def _first(mapping: Mapping[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in mapping and mapping[key] is not None:
            return mapping[key]
    return default


def _float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _evidence_level(value: Any, *, risk_group: bool = False) -> EvidenceLevel:
    """Map legacy labels and numeric scores to a foundation EvidenceLevel."""
    if isinstance(value, (int, float)):
        score = float(value)
        if score >= 85:
            return EvidenceLevel.STRONG
        if score >= 68:
            return EvidenceLevel.SUPPORTIVE
        if score >= 48:
            return EvidenceLevel.NEUTRAL
        if score >= 25:
            return EvidenceLevel.CAUTION
        return EvidenceLevel.REJECT

    label = _norm(value)
    if not label:
        return EvidenceLevel.MISSING

    strong = {
        "STRONG", "VERY_STRONG", "BULLISH", "READY", "GOOD",
        "SEHAT", "KUAT", "RENDAH" if risk_group else "__NONE__",
    }
    supportive = {
        "SUPPORTIVE", "POSITIVE", "FAVORABLE", "DEVELOPING",
        "MENDUKUNG", "NAIK", "MEDIUM_LOW" if risk_group else "__NONE__",
    }
    neutral = {"NEUTRAL", "MIXED", "SIDEWAYS", "DATAR", "WAIT", "WATCH"}
    caution = {
        "CAUTION", "WEAK", "UNFAVORABLE", "DETERIORATING",
        "WASPADA", "LEMAH", "TINGGI" if risk_group else "__NONE__",
    }
    reject = {
        "REJECT", "AVOID", "BAD", "EXTREME", "SUSPENDED",
        "HINDARI", "EKSTREM",
    }

    if label in strong:
        return EvidenceLevel.STRONG
    if label in supportive:
        return EvidenceLevel.SUPPORTIVE
    if label in neutral:
        return EvidenceLevel.NEUTRAL
    if label in caution:
        return EvidenceLevel.CAUTION
    if label in reject:
        return EvidenceLevel.REJECT
    return EvidenceLevel.MISSING


def _market_regime(market: Mapping[str, Any], root: Mapping[str, Any]) -> MarketRegime:
    value = _first(
        market,
        "regime", "market_regime", "posture", "market_posture",
        default=_first(root, "market_regime", "market_posture"),
    )
    label = _norm(value)

    mapping = {
        "BULL_EXPANSION": MarketRegime.BULL_EXPANSION,
        "EXPANSION": MarketRegime.BULL_EXPANSION,
        "BULLISH": MarketRegime.BULL_EXPANSION,
        "STRONG": MarketRegime.BULL_EXPANSION,
        "SELECTIVE": MarketRegime.BULL_WEAKENING,
        "BULL_WEAKENING": MarketRegime.BULL_WEAKENING,
        "SIDEWAYS": MarketRegime.SIDEWAYS,
        "NEUTRAL": MarketRegime.SIDEWAYS,
        "RECOVERY": MarketRegime.RECOVERY,
        "RECOVERING": MarketRegime.RECOVERY,
        "DISTRIBUTION": MarketRegime.DISTRIBUTION,
        "DEFENSIVE": MarketRegime.DISTRIBUTION,
        "PANIC": MarketRegime.PANIC,
        "CAPITULATION": MarketRegime.PANIC,
    }
    return mapping.get(label, MarketRegime.DATA_LIMITED)


def _candidate_rows(market: Mapping[str, Any]) -> Iterable[Mapping[str, Any]]:
    for key in ("candidates", "reviewed", "watchlist", "early", "opportunities"):
        value = market.get(key)
        if isinstance(value, list):
            for row in value:
                if isinstance(row, Mapping):
                    yield row


def _signal_value(row: Mapping[str, Any], group: str) -> Any:
    direct_keys = {
        "trend": ("trend", "trend_signal", "trend_score"),
        "momentum": ("momentum", "momentum_signal", "momentum_score", "rsi_state"),
        "volume": ("volume", "volume_signal", "volume_score", "rvol_state"),
        "liquidity": ("liquidity", "liquidity_signal", "liquidity_score"),
        "risk": ("risk", "risk_signal", "risk_score", "risk_reward"),
        "breakout": ("breakout", "resistance", "breakout_signal", "resistance_signal"),
        "relative_strength": (
            "relative_strength", "relative_strength_signal", "rs_signal", "rs_score",
        ),
        "market": ("market", "market_signal", "market_score"),
    }
    for key in direct_keys[group]:
        if key in row:
            value = row[key]
            if isinstance(value, Mapping):
                return _first(value, "status", "signal", "label", "score", "value")
            return value

    signals = row.get("signals")
    if isinstance(signals, Mapping):
        value = signals.get(group)
        if isinstance(value, Mapping):
            return _first(value, "status", "signal", "label", "score", "value")
        return value

    evidence = row.get("evidence")
    if isinstance(evidence, Mapping):
        value = evidence.get(group)
        if isinstance(value, Mapping):
            return _first(value, "status", "signal", "label", "score", "value")
        return value

    return None


def candidate_to_snapshot(
    row: Mapping[str, Any],
    *,
    market_name: str,
    regime: MarketRegime,
) -> StockSnapshot:
    symbol = str(_first(row, "symbol", "ticker", "code", default="UNKNOWN")).strip()
    evidence = EvidenceVector(
        trend=_evidence_level(_signal_value(row, "trend")),
        momentum=_evidence_level(_signal_value(row, "momentum")),
        volume=_evidence_level(_signal_value(row, "volume")),
        liquidity=_evidence_level(_signal_value(row, "liquidity")),
        risk=_evidence_level(_signal_value(row, "risk"), risk_group=True),
        breakout=_evidence_level(_signal_value(row, "breakout")),
        relative_strength=_evidence_level(_signal_value(row, "relative_strength")),
        market=_evidence_level(_signal_value(row, "market")),
        raw_metrics={
            "quality": _first(row, "quality", "quality_score", "score"),
            "close": _first(row, "close", "price", "last"),
            "rsi": _first(row, "rsi", "RSI"),
            "rvol": _first(row, "rvol", "RVOL", "relative_volume"),
        },
    )

    return StockSnapshot(
        symbol=symbol,
        market=market_name,
        regime=regime,
        evidence=evidence,
        price=_float(_first(row, "close", "price", "last")),
        resistance=_float(_first(row, "resistance", "watch_high", "entry_high")),
        support=_float(_first(row, "support", "stop", "invalidation")),
        is_held=bool(_first(row, "is_held", "held", default=False)),
    )


def integrate_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    decision_engine = DecisionEngine()
    explain_engine = ExplainEngine()

    output_markets: list[dict[str, Any]] = []
    markets = payload.get("markets")
    if not isinstance(markets, list):
        markets = []

    for market in markets:
        if not isinstance(market, Mapping):
            continue

        market_name = str(_first(market, "market", "name", default="UNKNOWN"))
        regime = _market_regime(market, payload)
        seen: set[str] = set()
        decisions: list[dict[str, Any]] = []

        for row in _candidate_rows(market):
            snapshot = candidate_to_snapshot(
                row, market_name=market_name, regime=regime
            )
            if snapshot.symbol in seen:
                continue
            seen.add(snapshot.symbol)

            decision = decision_engine.decide(snapshot)
            compact = explain_engine.compact_id(decision)
            compact["CAKUPAN"] = round(decision.coverage)
            compact["REGIME"] = regime.value
            compact["PEMICU"] = compact.get("PEMICU")
            decisions.append(compact)

        order = {
            "EKSEKUSI": 0,
            "SIAGA": 1,
            "AWAL": 2,
            "TAHAN": 3,
            "LEPAS": 4,
            "JUAL": 5,
            "LEWATI": 6,
            "DATA MINIM": 7,
        }
        decisions.sort(
            key=lambda item: (
                order.get(str(item.get("AKSI")), 99),
                -float(item.get("EVIDENCE") or 0),
                str(item.get("SIMBOL") or ""),
            )
        )

        counts: dict[str, int] = {}
        for item in decisions:
            action = str(item["AKSI"])
            counts[action] = counts.get(action, 0) + 1

        output_markets.append(
            {
                "PASAR": market_name,
                "REGIME": regime.value,
                "JUMLAH": len(decisions),
                "RINGKAS": counts,
                "KEPUTUSAN": decisions,
            }
        )

    return {
        "schema_version": 1,
        "generated_at": payload.get("generated_at"),
        "mode": payload.get("mode"),
        "source": payload.get("source"),
        "markets": output_markets,
    }


def integrate_file(input_path: str | Path, output_path: str | Path) -> dict[str, Any]:
    input_file = Path(input_path)
    output_file = Path(output_path)
    payload = json.loads(input_file.read_text(encoding="utf-8"))
    integrated = integrate_payload(payload)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(
        json.dumps(integrated, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return integrated
