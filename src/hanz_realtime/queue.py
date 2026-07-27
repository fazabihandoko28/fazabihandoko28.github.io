from __future__ import annotations

from datetime import datetime

from .models import QueueItem


class OpportunityQueue:
    def __init__(self, max_size: int = 50) -> None:
        self.max_size = max_size
        self._items: dict[tuple[str, str], QueueItem] = {}

    def upsert(
        self,
        symbol: str,
        market: str,
        score: float,
        reason: str,
        updated_at: datetime,
    ) -> None:
        self._items[(market, symbol)] = QueueItem(
            symbol=symbol,
            market=market,
            score=score,
            reason=reason,
            updated_at=updated_at,
        )
        if len(self._items) > self.max_size:
            keep = self.ranked()[: self.max_size]
            self._items = {(item.market, item.symbol): item for item in keep}

    def remove(self, market: str, symbol: str) -> None:
        self._items.pop((market, symbol), None)

    def ranked(self, limit: int | None = None) -> list[QueueItem]:
        items = sorted(
            self._items.values(),
            key=lambda item: (-item.score, item.market, item.symbol),
        )
        return items if limit is None else items[:limit]
