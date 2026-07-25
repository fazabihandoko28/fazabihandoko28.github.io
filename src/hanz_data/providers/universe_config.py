from __future__ import annotations

import csv
from pathlib import Path

from .yahoo_provider import YahooSymbol


def load_yahoo_universe(path: str | Path) -> tuple[YahooSymbol, ...]:
    file_path = Path(path)
    rows: list[YahooSymbol] = []
    with file_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"market", "symbol", "yahoo_ticker"}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError(f"Universe CSV must contain: {sorted(required)}")
        for row in reader:
            market = (row.get("market") or "").strip().upper()
            symbol = (row.get("symbol") or "").strip().upper()
            ticker = (row.get("yahoo_ticker") or "").strip()
            enabled = (row.get("enabled") or "true").strip().lower() not in {"0", "false", "no"}
            if enabled and market and symbol and ticker:
                rows.append(YahooSymbol(market=market, symbol=symbol, yahoo_ticker=ticker))
    if not rows:
        raise ValueError("No enabled symbols found in universe CSV")
    return tuple(rows)
