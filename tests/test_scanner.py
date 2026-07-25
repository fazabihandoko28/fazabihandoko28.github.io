import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from hanz_data import DirectoryCsvProvider
from hanz_scanner import MarketScanner


class TestScanner(unittest.TestCase):
    def write_symbol(self, root: Path, market: str, symbol: str, rising: bool = True):
        folder = root / market
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{symbol}.csv"
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        with path.open("w", encoding="utf-8") as handle:
            handle.write("datetime,open,high,low,close,volume\n")
            for index in range(80):
                close = 100 + (index * 0.5 if rising else -index * 0.2)
                volume = 2_000_000 + index * 10_000
                timestamp = (start + timedelta(days=index)).isoformat()
                handle.write(f"{timestamp},{close-0.2},{close+0.6},{close-0.8},{close},{volume}\n")

    def test_discovers_symbols_without_manual_ticker_input(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.write_symbol(root, "BEI", "AAA")
            self.write_symbol(root, "BEI", "BBB", rising=False)
            scanner = MarketScanner(DirectoryCsvProvider(root))
            results = scanner.scan_market("BEI")
            self.assertEqual({item.symbol for item in results}, {"AAA", "BBB"})
            self.assertEqual(len(results), 2)
