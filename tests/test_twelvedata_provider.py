from __future__ import annotations

import json
import unittest
from datetime import timezone

from hanz_providers.twelvedata import (
    TwelveDataConfig,
    TwelveDataMessageParser,
    TwelveDataProvider,
)
from hanz_realtime.models import Tick


class FakeConnection:
    def __init__(self):
        self.sent = []
        self.closed = False

    def send(self, payload):
        self.sent.append(json.loads(payload))

    def recv(self):
        raise RuntimeError("stop-test")

    def close(self):
        self.closed = True


class TwelveDataProviderTests(unittest.TestCase):
    def test_config_endpoint(self):
        config = TwelveDataConfig(
            api_key="secret",
            symbols=("TINS", "BMRI"),
        )
        self.assertIn("apikey=secret", config.endpoint())

    def test_price_message_maps_to_tick(self):
        parser = TwelveDataMessageParser(
            market="BEI",
            symbol_aliases={"TINS:IDX": "TINS"},
        )
        parsed = parser.parse(json.dumps({
            "event": "price",
            "symbol": "TINS:IDX",
            "price": 3440,
            "timestamp": 1785142800,
            "day_volume": 123456,
        }))
        self.assertIsInstance(parsed, Tick)
        self.assertEqual(parsed.symbol, "TINS")
        self.assertEqual(parsed.price, 3440)
        self.assertEqual(parsed.volume, 123456)
        self.assertEqual(parsed.timestamp.tzinfo, timezone.utc)

    def test_invalid_price_is_ignored(self):
        parser = TwelveDataMessageParser()
        parsed = parser.parse(json.dumps({
            "event": "price",
            "symbol": "TINS",
            "price": None,
            "timestamp": 1785142800,
        }))
        self.assertIsNone(parsed)

    def test_status_message_passes_through(self):
        parser = TwelveDataMessageParser()
        payload = {"event": "subscribe-status", "status": "ok"}
        self.assertEqual(parser.parse(json.dumps(payload)), payload)

    def test_subscribe_payload(self):
        connection = FakeConnection()
        provider = TwelveDataProvider(
            TwelveDataConfig(
                api_key="secret",
                symbols=("TINS", "BMRI"),
            ),
            on_tick=lambda tick: None,
            connection_factory=lambda url: connection,
            sleep=lambda seconds: None,
        )
        provider._subscribe(connection)
        self.assertEqual(
            connection.sent[0],
            {
                "action": "subscribe",
                "params": {"symbols": "TINS,BMRI"},
            },
        )

    def test_heartbeat_payload(self):
        connection = FakeConnection()
        TwelveDataProvider._heartbeat(connection)
        self.assertEqual(
            connection.sent[0],
            {"action": "heartbeat"},
        )

    def test_backoff_is_bounded(self):
        provider = TwelveDataProvider(
            TwelveDataConfig(
                api_key="secret",
                symbols=("TINS",),
                reconnect_min_seconds=1,
                reconnect_max_seconds=10,
            ),
            on_tick=lambda tick: None,
        )
        self.assertLessEqual(provider._backoff(20), 10)


if __name__ == "__main__":
    unittest.main()
