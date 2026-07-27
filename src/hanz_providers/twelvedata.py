from __future__ import annotations

import json
import os
import random
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Event
from typing import Callable, Iterable, Mapping, Protocol

from hanz_realtime.models import Tick


class WebSocketConnection(Protocol):
    def send(self, payload: str) -> object:
        ...
    def recv(self) -> str | bytes:
        ...
    def close(self) -> object:
        ...


ConnectionFactory = Callable[[str], WebSocketConnection]
TickCallback = Callable[[Tick], None]
StatusCallback = Callable[[dict], None]


@dataclass(frozen=True)
class TwelveDataConfig:
    api_key: str
    symbols: tuple[str, ...]
    market: str = "BEI"
    source: str = "TWELVE_DATA"
    websocket_url: str = "wss://ws.twelvedata.com/v1/quotes/price"
    heartbeat_seconds: int = 10
    reconnect_min_seconds: float = 1.0
    reconnect_max_seconds: float = 30.0

    @classmethod
    def from_env(
        cls,
        symbols: Iterable[str] | None = None,
        market: str = "BEI",
    ) -> "TwelveDataConfig":
        api_key = os.getenv("HANZ_TWELVEDATA_API_KEY", "").strip()
        if not api_key:
            raise ValueError("HANZ_TWELVEDATA_API_KEY is required")

        if symbols is None:
            raw = os.getenv("HANZ_TWELVEDATA_SYMBOLS", "")
            symbols = [item.strip() for item in raw.split(",") if item.strip()]

        normalized = tuple(dict.fromkeys(str(item).strip() for item in symbols))
        if not normalized:
            raise ValueError("At least one Twelve Data symbol is required")

        return cls(
            api_key=api_key,
            symbols=normalized,
            market=market,
        )

    def endpoint(self) -> str:
        return f"{self.websocket_url}?apikey={self.api_key}"


class TwelveDataMessageParser:
    """Convert Twelve Data WebSocket messages into normalized HANZ ticks."""

    def __init__(
        self,
        *,
        market: str = "BEI",
        source: str = "TWELVE_DATA",
        symbol_aliases: Mapping[str, str] | None = None,
    ) -> None:
        self.market = market
        self.source = source
        self.symbol_aliases = {
            str(key): str(value).upper()
            for key, value in (symbol_aliases or {}).items()
        }
        self._last_cumulative_volume: dict[str, float] = {}

    def parse(self, raw: str | bytes) -> Tick | dict | None:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        payload = json.loads(raw)

        event = str(payload.get("event") or payload.get("type") or "").lower()
        if event in {"subscribe-status", "status", "heartbeat"}:
            return payload

        if event != "price":
            return None

        raw_symbol = str(payload.get("symbol") or "").strip()
        price = _to_float(payload.get("price"))
        timestamp = _to_timestamp(
            payload.get("timestamp")
            or payload.get("datetime")
            or payload.get("time")
        )
        if not raw_symbol or price is None or price <= 0 or timestamp is None:
            return None

        cumulative_volume = _to_float(
            payload.get("day_volume")
            or payload.get("volume")
            or payload.get("dayVolume")
        )
        symbol = self.symbol_aliases.get(raw_symbol, _clean_symbol(raw_symbol))

        previous = self._last_cumulative_volume.get(raw_symbol)
        if cumulative_volume is None:
            normalized_volume = previous or 0.0
        elif previous is not None and cumulative_volume < previous:
            # New session or provider counter reset.
            normalized_volume = cumulative_volume
        else:
            normalized_volume = cumulative_volume

        if cumulative_volume is not None:
            self._last_cumulative_volume[raw_symbol] = cumulative_volume

        return Tick(
            symbol=symbol,
            market=self.market,
            price=price,
            volume=normalized_volume,
            timestamp=timestamp,
            source=self.source,
        )


class TwelveDataProvider:
    """Resilient Twelve Data WebSocket provider.

    The provider supplies normalized ticks to RealtimeGateway. It does not make
    trading decisions and does not expose the API key to dashboard clients.
    """

    def __init__(
        self,
        config: TwelveDataConfig,
        *,
        on_tick: TickCallback,
        on_status: StatusCallback | None = None,
        connection_factory: ConnectionFactory | None = None,
        parser: TwelveDataMessageParser | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.config = config
        self.on_tick = on_tick
        self.on_status = on_status or (lambda payload: None)
        self.connection_factory = connection_factory or _default_connection
        self.parser = parser or TwelveDataMessageParser(
            market=config.market,
            source=config.source,
        )
        self.sleep = sleep
        self._stop = Event()

    def stop(self) -> None:
        self._stop.set()

    def run_forever(self) -> None:
        attempt = 0

        while not self._stop.is_set():
            connection = None
            try:
                connection = self.connection_factory(self.config.endpoint())
                self._subscribe(connection)
                attempt = 0
                last_heartbeat = time.monotonic()

                while not self._stop.is_set():
                    if (
                        time.monotonic() - last_heartbeat
                        >= self.config.heartbeat_seconds
                    ):
                        self._heartbeat(connection)
                        last_heartbeat = time.monotonic()

                    raw = connection.recv()
                    parsed = self.parser.parse(raw)
                    if isinstance(parsed, Tick):
                        self.on_tick(parsed)
                    elif isinstance(parsed, dict):
                        self.on_status(parsed)

            except Exception as exc:
                attempt += 1
                self.on_status({
                    "event": "provider-error",
                    "provider": self.config.source,
                    "attempt": attempt,
                    "error": str(exc),
                })
                if not self._stop.is_set():
                    self.sleep(self._backoff(attempt))
            finally:
                if connection is not None:
                    try:
                        connection.close()
                    except Exception:
                        pass

    def _subscribe(self, connection: WebSocketConnection) -> None:
        connection.send(json.dumps({
            "action": "subscribe",
            "params": {
                "symbols": ",".join(self.config.symbols),
            },
        }))

    @staticmethod
    def _heartbeat(connection: WebSocketConnection) -> None:
        connection.send(json.dumps({"action": "heartbeat"}))

    def _backoff(self, attempt: int) -> float:
        ceiling = min(
            self.config.reconnect_max_seconds,
            self.config.reconnect_min_seconds * (2 ** max(attempt - 1, 0)),
        )
        return min(
            self.config.reconnect_max_seconds,
            ceiling + random.uniform(0.0, ceiling * 0.15),
        )


def _default_connection(url: str) -> WebSocketConnection:
    try:
        import websocket
    except ImportError as exc:
        raise RuntimeError(
            "Install dependency: websocket-client>=1.8,<2"
        ) from exc
    return websocket.create_connection(url, timeout=30)


def _clean_symbol(raw_symbol: str) -> str:
    value = raw_symbol.upper().strip()
    for separator in (":", "/"):
        if separator in value:
            value = value.split(separator)[0]
    if "." in value:
        value = value.split(".")[0]
    return value


def _to_float(value) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_timestamp(value) -> datetime | None:
    try:
        if value is None:
            return None
        numeric = float(value)
        if numeric > 10_000_000_000:
            numeric /= 1000.0
        return datetime.fromtimestamp(numeric, tz=timezone.utc)
    except (TypeError, ValueError, OSError, OverflowError):
        return None
