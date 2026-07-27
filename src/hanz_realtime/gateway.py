from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from math import isfinite
from statistics import mean, pstdev
from typing import Callable

from .models import SymbolState, Tick
from .queue import OpportunityQueue
from .rolling import PricePoint, RollingWindow
from .scheduler import SmartScheduler


DecisionCallback = Callable[[SymbolState], None]


class RealtimeGateway:
    """Incremental tick processor.

    This module does not open a market-data connection itself. It validates and
    consumes normalized ticks from any provider adapter.
    """

    def __init__(
        self,
        scheduler: SmartScheduler | None = None,
        queue: OpportunityQueue | None = None,
        on_candidate: DecisionCallback | None = None,
    ) -> None:
        self.scheduler = scheduler or SmartScheduler()
        self.queue = queue or OpportunityQueue()
        self.on_candidate = on_candidate
        self.states: dict[tuple[str, str], SymbolState] = {}
        self.windows: dict[tuple[str, str], RollingWindow] = defaultdict(
            lambda: RollingWindow(max_points=300, max_age_seconds=300)
        )

    def ingest(self, tick: Tick) -> SymbolState:
        self._validate_tick(tick)
        key = (tick.market, tick.symbol)
        state = self.states.get(key)
        if state is None:
            state = SymbolState(symbol=tick.symbol, market=tick.market)
            self.states[key] = state

        previous_price = state.last_price
        previous_time = state.last_timestamp
        incremental_volume = max(0.0, tick.volume - state.last_volume)

        state.tick_count += 1
        state.cumulative_volume += incremental_volume
        state.last_price = tick.price
        state.last_volume = tick.volume
        state.last_timestamp = tick.timestamp

        if previous_price and previous_price > 0:
            state.price_change_pct = ((tick.price / previous_price) - 1.0) * 100.0

        if previous_time and tick.timestamp > previous_time:
            seconds = (tick.timestamp - previous_time).total_seconds()
            if seconds > 0 and previous_price:
                state.velocity = (tick.price - previous_price) / seconds

        if tick.bid is not None and tick.ask is not None and tick.ask > 0:
            state.spread_pct = ((tick.ask - tick.bid) / tick.ask) * 100.0

        window = self.windows[key]
        window.add(PricePoint(tick.timestamp, tick.price, tick.volume))
        state.anomaly_score = self._anomaly_score(window, state)
        state.dirty_flags.update({"price", "volume"})

        if state.anomaly_score >= 55.0:
            self.queue.upsert(
                symbol=tick.symbol,
                market=tick.market,
                score=state.anomaly_score,
                reason=self._reason(state),
                updated_at=tick.timestamp,
            )
            if self.on_candidate is not None:
                self.on_candidate(state)
        elif state.anomaly_score < 35.0:
            self.queue.remove(tick.market, tick.symbol)

        return state

    @staticmethod
    def _validate_tick(tick: Tick) -> None:
        if not tick.symbol.strip():
            raise ValueError("symbol is required")
        if not tick.market.strip():
            raise ValueError("market is required")
        if not isfinite(tick.price) or tick.price <= 0:
            raise ValueError("price must be positive and finite")
        if not isfinite(tick.volume) or tick.volume < 0:
            raise ValueError("volume must be non-negative and finite")

    @staticmethod
    def _anomaly_score(window: RollingWindow, state: SymbolState) -> float:
        prices = window.prices()
        volumes = window.volumes()

        if len(prices) < 3:
            return 0.0

        first = prices[0]
        last = prices[-1]
        move_pct = abs((last / first - 1.0) * 100.0) if first else 0.0

        average_volume = mean(volumes[:-1]) if len(volumes) > 1 else volumes[-1]
        volume_ratio = volumes[-1] / average_volume if average_volume > 0 else 1.0

        volatility = pstdev(prices) / mean(prices) * 100.0 if mean(prices) else 0.0
        spread_penalty = min((state.spread_pct or 0.0) * 8.0, 20.0)

        score = (
            min(move_pct * 18.0, 35.0)
            + min(max(volume_ratio - 1.0, 0.0) * 20.0, 35.0)
            + min(volatility * 10.0, 20.0)
            + min(abs(state.velocity) * 2.0, 10.0)
            - spread_penalty
        )
        return round(max(0.0, min(score, 100.0)), 2)

    @staticmethod
    def _reason(state: SymbolState) -> str:
        if state.anomaly_score >= 80:
            return "ANOMALI KUAT"
        if state.anomaly_score >= 65:
            return "MENGUAT"
        return "PANTAU"
