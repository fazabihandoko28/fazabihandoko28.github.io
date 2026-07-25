from __future__ import annotations

import unittest

from hanz_data.providers.base import MarketDataProvider
from hanz_data.providers.registry import ProviderRegistry


class EmptyProvider(MarketDataProvider):
    def list_symbols(self, market):
        return []

    def load_series(self, market, symbol, *, start=None, end=None):
        raise NotImplementedError


class ProviderRegistryTests(unittest.TestCase):
    def test_register_and_resolve(self):
        registry = ProviderRegistry()
        provider = EmptyProvider()
        registry.register("bei", provider)
        self.assertIs(registry.get("BEI"), provider)
        self.assertEqual(registry.markets(), ("BEI",))

    def test_missing_market_is_explicit(self):
        registry = ProviderRegistry()
        with self.assertRaisesRegex(KeyError, "no provider registered"):
            registry.get("ADX")


if __name__ == "__main__":
    unittest.main()
