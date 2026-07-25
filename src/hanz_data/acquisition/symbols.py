from __future__ import annotations


class SymbolNormalizer:
    """Normalizes Commander-facing symbols while keeping vendor mapping configurable."""

    def __init__(self, suffixes: dict[str, str] | None = None) -> None:
        self.suffixes = {key.upper(): value for key, value in (suffixes or {}).items()}

    def canonical(self, market: str, symbol: str) -> str:
        market_key = market.upper().strip()
        cleaned = symbol.upper().strip().replace(" ", "")
        suffix = self.suffixes.get(market_key, "")
        if suffix and not cleaned.endswith(suffix.upper()):
            return f"{cleaned}{suffix}"
        return cleaned
