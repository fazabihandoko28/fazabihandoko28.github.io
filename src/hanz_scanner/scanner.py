from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Iterable

from hanz_core import Decision, EntryStatus, decide_entry
from hanz_data import MarketDataProvider, validate_series
from hanz_technical import TechnicalSnapshot, build_technical_snapshot


@dataclass(frozen=True, slots=True)
class ScanResult:
    symbol: str
    market: str
    decision: Decision
    snapshot: TechnicalSnapshot | None
    error: str | None = None


class MarketScanner:
    """Discovers every available symbol from a provider and ranks decisions."""

    _priority = {
        EntryStatus.READY: 0,
        EntryStatus.WAIT: 1,
        EntryStatus.HIGH_RISK: 2,
        EntryStatus.REJECT: 3,
    }

    def __init__(self, provider: MarketDataProvider, *, minimum_bars: int = 60) -> None:
        self.provider = provider
        self.minimum_bars = minimum_bars

    def scan_market(self, market: str) -> list[ScanResult]:
        results: list[ScanResult] = []
        for symbol in self.provider.list_symbols(market):
            try:
                series = self.provider.load_series(market, symbol)
                report = validate_series(series, minimum_bars=self.minimum_bars)
                snapshot = build_technical_snapshot(series, report)
                decision = decide_entry(snapshot.evidence)
                results.append(ScanResult(symbol, market.upper(), decision, snapshot))
            except Exception as exc:  # provider isolation: one bad symbol cannot stop the market scan
                results.append(
                    ScanResult(
                        symbol=symbol,
                        market=market.upper(),
                        decision=Decision(status=EntryStatus.WAIT, reasons=["Data processing failed"], audit={"error": str(exc)}),
                        snapshot=None,
                        error=str(exc),
                    )
                )
        return sorted(results, key=lambda item: (self._priority[item.decision.status], item.symbol))

    def scan_markets(self, markets: Iterable[str]) -> list[ScanResult]:
        combined: list[ScanResult] = []
        for market in markets:
            combined.extend(self.scan_market(market))
        return sorted(combined, key=lambda item: (self._priority[item.decision.status], item.market, item.symbol))
