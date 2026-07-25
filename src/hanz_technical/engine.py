from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from hanz_core import Evidence, Signal
from hanz_data import MarketSeries, ValidationReport
from .indicators import atr, ema, relative_volume, rolling_high, rolling_low, rsi


@dataclass(frozen=True, slots=True)
class TechnicalSnapshot:
    symbol: str
    market: str
    timestamp: datetime
    close: float
    ema20: float | None
    ema50: float | None
    rsi14: float | None
    atr14: float | None
    relative_volume20: float | None
    resistance20: float | None
    support20: float | None
    evidence: tuple[Evidence, ...]


def _e(name: str, signal: Signal, timestamp: datetime, detail: str, source: str = "technical_engine", critical: bool = False) -> Evidence:
    return Evidence(name=name, signal=signal, source=source, timestamp=timestamp.astimezone(timezone.utc).isoformat(), detail=detail, critical=critical)


def build_technical_snapshot(series: MarketSeries, report: ValidationReport) -> TechnicalSnapshot:
    if not series.bars:
        raise ValueError("series has no bars")

    closes = [bar.close for bar in series.bars]
    highs = [bar.high for bar in series.bars]
    lows = [bar.low for bar in series.bars]
    volumes = [bar.volume for bar in series.bars]
    latest = series.bars[-1]

    ema20 = ema(closes, 20)
    ema50 = ema(closes, 50)
    rsi14 = rsi(closes, 14)
    atr14 = atr(highs, lows, closes, 14)
    rvol = relative_volume(volumes, 20)
    resistance = rolling_high(highs, 20)
    support = rolling_low(lows, 20)

    evidence: list[Evidence] = []
    evidence.append(_e("data_freshness", Signal.POSITIVE if report.valid else Signal.NEGATIVE, latest.timestamp, "valid" if report.valid else ";".join(report.errors), critical=True))

    avg_value = sum(bar.close * bar.volume for bar in series.bars[-20:]) / min(20, len(series.bars))
    if avg_value <= 0:
        liquidity_signal = Signal.UNKNOWN
    elif avg_value >= 1_000_000_000:
        liquidity_signal = Signal.POSITIVE
    elif avg_value >= 100_000_000:
        liquidity_signal = Signal.NEUTRAL
    else:
        liquidity_signal = Signal.NEGATIVE
    evidence.append(_e("liquidity", liquidity_signal, latest.timestamp, f"avg_value20={avg_value:.2f}", critical=True))

    if ema20 is None or ema50 is None:
        trend_signal = Signal.UNKNOWN
        trend_detail = "insufficient_history"
    elif latest.close > ema20 > ema50:
        trend_signal = Signal.POSITIVE
        trend_detail = f"close>{ema20:.4f}>{ema50:.4f}"
    elif latest.close < ema20 < ema50:
        trend_signal = Signal.NEGATIVE
        trend_detail = f"close<{ema20:.4f}<{ema50:.4f}"
    else:
        trend_signal = Signal.WARNING
        trend_detail = f"mixed close={latest.close:.4f},ema20={ema20:.4f},ema50={ema50:.4f}"
    evidence.append(_e("price_structure", trend_signal, latest.timestamp, trend_detail))

    if rvol is None:
        volume_signal = Signal.UNKNOWN
        volume_detail = "insufficient_history"
    elif rvol >= 1.5:
        volume_signal = Signal.POSITIVE
        volume_detail = f"rvol20={rvol:.2f}"
    elif rvol >= 0.8:
        volume_signal = Signal.NEUTRAL
        volume_detail = f"rvol20={rvol:.2f}"
    else:
        volume_signal = Signal.WARNING
        volume_detail = f"rvol20={rvol:.2f}"
    evidence.append(_e("volume_confirmation", volume_signal, latest.timestamp, volume_detail))

    if resistance is None:
        resistance_signal = Signal.UNKNOWN
        resistance_detail = "insufficient_history"
    elif latest.close > resistance:
        resistance_signal = Signal.POSITIVE
        resistance_detail = f"breakout close={latest.close:.4f}>resistance20={resistance:.4f}"
    elif resistance > 0 and (resistance - latest.close) / resistance <= 0.015:
        resistance_signal = Signal.WARNING
        resistance_detail = f"near resistance20={resistance:.4f}"
    else:
        resistance_signal = Signal.NEUTRAL
        resistance_detail = f"room_to_resistance20={resistance:.4f}"
    evidence.append(_e("resistance", resistance_signal, latest.timestamp, resistance_detail))

    if support is None or atr14 is None:
        rr_signal = Signal.UNKNOWN
        rr_detail = "insufficient_history"
    else:
        risk = max(latest.close - support, atr14)
        reward = max((resistance or latest.close) - latest.close, 0.0)
        ratio = reward / risk if risk > 0 else 0.0
        if latest.close > (resistance or float("inf")):
            ratio = 2.0
        if ratio >= 1.8:
            rr_signal = Signal.POSITIVE
        elif ratio >= 1.0:
            rr_signal = Signal.WARNING
        else:
            rr_signal = Signal.NEGATIVE
        rr_detail = f"proxy_rr={ratio:.2f};support20={support:.4f};atr14={atr14:.4f}"
    evidence.append(_e("risk_reward", rr_signal, latest.timestamp, rr_detail, critical=True))

    if rsi14 is None:
        extension_signal = Signal.UNKNOWN
        extension_detail = "insufficient_history"
    elif rsi14 >= 80:
        extension_signal = Signal.NEGATIVE
        extension_detail = f"rsi14={rsi14:.2f}"
    elif rsi14 >= 70:
        extension_signal = Signal.WARNING
        extension_detail = f"rsi14={rsi14:.2f}"
    else:
        extension_signal = Signal.NEUTRAL
        extension_detail = f"rsi14={rsi14:.2f}"
    evidence.append(_e("extension_risk", extension_signal, latest.timestamp, extension_detail))

    # Market regime is intentionally neutral until an index series is connected.
    evidence.append(_e("market_regime", Signal.NEUTRAL, latest.timestamp, "index_adapter_not_connected"))

    return TechnicalSnapshot(
        symbol=series.symbol,
        market=series.market,
        timestamp=latest.timestamp,
        close=latest.close,
        ema20=ema20,
        ema50=ema50,
        rsi14=rsi14,
        atr14=atr14,
        relative_volume20=rvol,
        resistance20=resistance,
        support20=support,
        evidence=tuple(evidence),
    )
