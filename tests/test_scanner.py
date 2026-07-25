from bootstrap import PROJECT_ROOT  # noqa: F401

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


from hanz_core import EntryStatus
from hanz_data import DirectoryCsvProvider
from hanz_scanner import CandidateTier, MarketScanner


class TestScanner(unittest.TestCase):
    def write_symbol(
        self,
        root: Path,
        market: str,
        symbol: str,
        *,
        slope: float = 0.5,
        latest_volume_multiplier: float = 2.0,
        base_volume: float = 2_000_000,
        malformed: bool = False,
    ) -> None:
        folder = root / market
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{symbol}.csv"
        if malformed:
            path.write_text("datetime,open,high,low,close,volume\nnot-a-date,1,2,0,1,1\n", encoding="utf-8")
            return
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        with path.open("w", encoding="utf-8") as handle:
            handle.write("datetime,open,high,low,close,volume\n")
            for index in range(80):
                close = 100 + index * slope
                volume = base_volume
                if index == 79:
                    volume *= latest_volume_multiplier
                    close += max(2.0, abs(slope) * 5)
                timestamp = (start + timedelta(days=index)).isoformat()
                handle.write(f"{timestamp},{close-0.2},{close+0.6},{close-0.8},{close},{volume}\n")

    def test_discovers_symbols_without_manual_ticker_input(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.write_symbol(root, "BEI", "AAA")
            self.write_symbol(root, "BEI", "BBB", slope=-0.2)
            report = MarketScanner(DirectoryCsvProvider(root)).scan_market("BEI")
            discovered = {
                item.symbol
                for group in (report.candidates, report.reviewed, report.rejected, report.errors)
                for item in group
            }
            self.assertEqual(discovered, {"AAA", "BBB"})
            self.assertEqual(report.universe_size, 2)

    def test_candidate_limit_is_enforced(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for index in range(8):
                self.write_symbol(root, "BEI", f"S{index:02d}", slope=0.4 + index * 0.02)
            report = MarketScanner(DirectoryCsvProvider(root), candidate_limit=3).scan_market("BEI")
            self.assertLessEqual(len(report.candidates), 3)

    def test_low_liquidity_is_disqualified(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.write_symbol(root, "BEI", "ILLIQ", base_volume=10)
            report = MarketScanner(DirectoryCsvProvider(root)).scan_market("BEI")
            self.assertEqual(len(report.rejected), 1)
            self.assertEqual(report.rejected[0].decision.status, EntryStatus.REJECT)
            self.assertIn("liquidity", report.rejected[0].decision.vetoes)

    def test_bad_symbol_is_isolated(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.write_symbol(root, "BEI", "GOOD")
            self.write_symbol(root, "BEI", "BAD", malformed=True)
            report = MarketScanner(DirectoryCsvProvider(root)).scan_market("BEI")
            self.assertEqual(len(report.errors), 1)
            self.assertEqual(report.errors[0].symbol, "BAD")
            self.assertEqual(report.errors[0].tier, CandidateTier.DATA_ERROR)
            self.assertEqual(report.universe_size, 2)

    def test_ranking_is_deterministic(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.write_symbol(root, "BEI", "AAA", latest_volume_multiplier=2.2)
            self.write_symbol(root, "BEI", "BBB", latest_volume_multiplier=3.0)
            scanner = MarketScanner(DirectoryCsvProvider(root), candidate_limit=5)
            first = [item.symbol for item in scanner.scan_market("BEI").candidates]
            second = [item.symbol for item in scanner.scan_market("BEI").candidates]
            self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
