from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from hanz_data.models import Bar, MarketSeries
from .base import MarketDataProvider


_REQUIRED = {"datetime", "open", "high", "low", "close", "volume"}


def _parse_time(value: str) -> datetime:
    text = value.strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


class DirectoryCsvProvider(MarketDataProvider):
    """
    Reads one CSV per symbol from <root>/<MARKET>/<SYMBOL>.csv.
    Symbols are discovered automatically; Commander does not enter tickers.
    """

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def list_symbols(self, market: str) -> Iterable[str]:
        folder = self.root / market.upper()
        if not folder.exists():
            return []
        return sorted(path.stem.upper() for path in folder.glob("*.csv"))

    def load_series(
        self,
        market: str,
        symbol: str,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> MarketSeries:
        path = self.root / market.upper() / f"{symbol.upper()}.csv"
        if not path.exists():
            raise FileNotFoundError(path)

        bars: list[Bar] = []
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            fields = {field.strip().lower() for field in (reader.fieldnames or [])}
            missing = _REQUIRED - fields
            if missing:
                raise ValueError(f"CSV {path} missing columns: {sorted(missing)}")

            for row in reader:
                normalized = {key.strip().lower(): value for key, value in row.items() if key}
                timestamp = _parse_time(normalized["datetime"])
                if start and timestamp < start:
                    continue
                if end and timestamp > end:
                    continue
                bars.append(
                    Bar(
                        symbol=symbol.upper(),
                        market=market.upper(),
                        timestamp=timestamp,
                        open=float(normalized["open"]),
                        high=float(normalized["high"]),
                        low=float(normalized["low"]),
                        close=float(normalized["close"]),
                        volume=float(normalized["volume"]),
                    )
                )
        return MarketSeries.from_iterable(symbol.upper(), market.upper(), bars)
