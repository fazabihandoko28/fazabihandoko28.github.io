from __future__ import annotations

import csv
from pathlib import Path


def load_symbol_map(path: str | Path) -> dict[str, str]:
    """Load provider_symbol -> HANZ symbol aliases from CSV."""
    result: dict[str, str] = {}
    with Path(path).open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            provider_symbol = str(row.get("provider_symbol") or "").strip()
            hanz_symbol = str(row.get("hanz_symbol") or "").strip().upper()
            if provider_symbol and hanz_symbol:
                result[provider_symbol] = hanz_symbol
    return result
