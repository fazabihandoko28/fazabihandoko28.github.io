from __future__ import annotations

import json
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


def _market_regime(market: Mapping[str, Any], root: Mapping[str, Any]) -> MarketRegime:
    label = _norm(_first(
        market,
        "regime", "market_regime", "posture", "market_posture",
        default=_first(root, "market_regime", "market_posture"),
    ))
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


def _bucket_level(row: Mapping[str, Any], evidence_name: str) -> EvidenceLevel:
    evidence = row.get("evidence")
    if not isinstance(evidence, Mapping):
        return EvidenceLevel.MISSING

    if evidence_name in set(evidence.get("positive") or []):
        return EvidenceLevel.STRONG
    if evidence_name in set(evidence.get("neutral") or []):
        return EvidenceLevel.NEUTRAL
    if evidence_name in set(evidence.get("warning") or []):
        return EvidenceLevel.CAUTION
    if evidence_name in set(evidence.get("negative") or []):
        return EvidenceLevel.REJECT
    return EvidenceLevel.MISSING


def _merge_levels(levels: Iterable[EvidenceLevel]) -> EvidenceLevel:
    values = [level for level in levels if level != EvidenceLevel.MISSING]
    if not values:
        return EvidenceLevel.MISSING
    for level in (
        EvidenceLevel.REJECT,
        EvidenceLevel.CAUTION,
        EvidenceLevel.NEUTRAL,
        EvidenceLevel.SUPPORTIVE,
        EvidenceLevel.STRONG,
    ):
        if level in values:
            return level
    return EvidenceLevel.MISSING


def _technical(row: Mapping[str, Any]) -> Mapping[str, Any]:
    value = row.get("technical")
    return value if isinstance(value, Mapping) else {}


def _trend_level(row: Mapping[str, Any]) -> EvidenceLevel:
    bucket = _bucket_level(row, "price_structure")
    if bucket != EvidenceLevel.MISSING:
        return bucket

    tech = _technical(row)
    close = _float(_first(row, "signal_close", "close", "price"))
    ema20 = _float(tech.get("ema20"))
    ema50 = _float(tech.get("ema50"))
    if close is None or ema20 is None or ema50 is None:
        return EvidenceLevel.MISSING
    if close > ema20 > ema50:
        return EvidenceLevel.STRONG
    if close > ema50:
        return EvidenceLevel.SUPPORTIVE
    if close < ema20 < ema50:
        return EvidenceLevel.REJECT
    return EvidenceLevel.CAUTION


def _momentum_level(row: Mapping[str, Any]) -> EvidenceLevel:
    rsi = _float(_technical(row).get("rsi14"))
    if rsi is None:
        return EvidenceLevel.MISSING
    if 55 <= rsi <= 70:
        return EvidenceLevel.STRONG
    if 48 <= rsi < 55:
        return EvidenceLevel.SUPPORTIVE
    if 42 <= rsi < 48 or 70 < rsi <= 78:
        return EvidenceLevel.NEUTRAL
    if 30 <= rsi < 42 or 78 < rsi <= 85:
        return EvidenceLevel.CAUTION
    return EvidenceLevel.REJECT


def _volume_level(row: Mapping[str, Any]) -> EvidenceLevel:
    bucket = _bucket_level(row, "volume_confirmation")
    if bucket != EvidenceLevel.MISSING:
        return bucket

    rvol = _float(_technical(row).get("relative_volume20"))
    if rvol is None:
        return EvidenceLevel.MISSING
    if rvol >= 1.8:
        return EvidenceLevel.STRONG
    if rvol >= 1.2:
        return EvidenceLevel.SUPPORTIVE
    if rvol >= 0.8:
        return EvidenceLevel.NEUTRAL
    if rvol >= 0.5:
        return EvidenceLevel.CAUTION
    return EvidenceLevel.REJECT


def _risk_level(row: Mapping[str, Any]) -> EvidenceLevel:
    entry_status = _norm(row.get("entry_status"))
    if entry_status in {"LOW_RISK", "READY"}:
        base = EvidenceLevel.STRONG
    elif entry_status in {"MODERATE_RISK", "MEDIUM_RISK", "OBSERVE"}:
        base = EvidenceLevel.SUPPORTIVE
    elif entry_status in {"HIGH_RISK", "CAUTION"}:
        base = EvidenceLevel.CAUTION
    elif entry_status in {"REJECT", "AVOID"}:
        base = EvidenceLevel.REJECT
    else:
        base = EvidenceLevel.MISSING

    return _merge_levels([base, _bucket_level(row, "risk_reward")])


def candidate_to_snapshot(
    row: Mapping[str, Any],
    *,
    market_name: str,
    regime: MarketRegime,
) -> StockSnapshot:
    tech = _technical(row)
    symbol = str(_first(row, "symbol", "ticker", "code", default="UNKNOWN")).strip()

    evidence = EvidenceVector(
        trend=_trend_level(row),
        momentum=_momentum_level(row),
        volume=_volume_level(row),
        liquidity=_bucket_level(row, "liquidity"),
        risk=_risk_level(row),
        breakout=_bucket_level(row, "resistance"),
        relative_strength=EvidenceLevel.MISSING,
        market=_bucket_level(row, "market_regime"),
        raw_metrics={
            "tier": row.get("tier"),
            "entry_status": row.get("entry_status"),
            "close": _first(row, "signal_close", "close", "price"),
            "ema20": tech.get("ema20"),
            "ema50": tech.get("ema50"),
            "rsi14": tech.get("rsi14"),
            "atr14": tech.get("atr14"),
            "relative_volume20": tech.get("relative_volume20"),
            "resistance20": tech.get("resistance20"),
            "support20": tech.get("support20"),
        },
    )

    return StockSnapshot(
        symbol=symbol,
        market=market_name,
        regime=regime,
        evidence=evidence,
        price=_float(_first(row, "signal_close", "close", "price")),
        resistance=_float(tech.get("resistance20")),
        support=_float(tech.get("support20")),
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

        output_markets.append({
            "PASAR": market_name,
            "REGIME": regime.value,
            "JUMLAH": len(decisions),
            "RINGKAS": counts,
            "KEPUTUSAN": decisions,
        })

    return {
        "schema_version": 2,
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
