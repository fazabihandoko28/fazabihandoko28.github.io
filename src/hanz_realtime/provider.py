from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable

from .models import Tick


class TickProvider(ABC):
    """Provider contract for real-time or replay feeds."""

    @abstractmethod
    def stream(self) -> Iterable[Tick]:
        raise NotImplementedError


class ReplayProvider(TickProvider):
    def __init__(self, ticks: Iterable[Tick]) -> None:
        self._ticks = list(ticks)

    def stream(self) -> Iterable[Tick]:
        yield from self._ticks
