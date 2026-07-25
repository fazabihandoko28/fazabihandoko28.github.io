from __future__ import annotations

import csv
import hashlib
from datetime import datetime
from pathlib import Path

from hanz_data.models import Bar, MarketSeries


class FileSeriesCache:
    """Transparent file cache. A cache entry is never trusted without validation."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, market: str, symbol: str, start: datetime | None, end: datetime | None) -> Path:
        raw = "|".join(
            [market.upper(), symbol.upper(), start.isoformat() if start else "", end.isoformat() if end else ""]
        )
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]
        return self.root / f"{market.upper()}_{symbol.upper()}_{digest}.csv"

    def get(self, market: str, symbol: str, start: datetime | None, end: datetime | None) -> MarketSeries | None:
        path = self._path(market, symbol, start, end)
        if not path.exists():
            return None
        bars: list[Bar] = []
        with path.open("r", encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                bars.append(
                    Bar(
                        symbol=row["symbol"],
                        market=row["market"],
                        timestamp=datetime.fromisoformat(row["timestamp"]),
                        open=float(row["open"]),
                        high=float(row["high"]),
                        low=float(row["low"]),
                        close=float(row["close"]),
                        volume=float(row["volume"]),
                    )
                )
        return MarketSeries.from_iterable(symbol=symbol, market=market, bars=bars)

    def put(self, series: MarketSeries, start: datetime | None, end: datetime | None) -> Path:
        path = self._path(series.market, series.symbol, start, end)
        temp = path.with_suffix(".tmp")
        with temp.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=["market", "symbol", "timestamp", "open", "high", "low", "close", "volume"],
            )
            writer.writeheader()
            for bar in series.bars:
                writer.writerow(
                    {
                        "market": series.market,
                        "symbol": series.symbol,
                        "timestamp": bar.timestamp.isoformat(),
                        "open": bar.open,
                        "high": bar.high,
                        "low": bar.low,
                        "close": bar.close,
                        "volume": bar.volume,
                    }
                )
        temp.replace(path)
        return path
