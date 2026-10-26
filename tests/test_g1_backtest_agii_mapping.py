"""G1-only regression: selected AGII must resolve to a research-only history provider."""
import unittest

from hanz_data import YahooSymbol
from hanz_app.research.generate_top5_5y_backtest import _research_mappings


class G1BacktestAGIIMappingTests(unittest.TestCase):
    def test_agii_has_explicit_research_only_yahoo_mapping(self):
        available = _research_mappings([])
        self.assertIn("AGII", available)
        self.assertEqual(available["AGII"].market, "BEI")
        self.assertEqual(available["AGII"].symbol, "AGII")
        self.assertEqual(available["AGII"].yahoo_ticker, "AGII.JK")

    def test_explicit_agii_mapping_takes_precedence(self):
        explicit = YahooSymbol(market="BEI", symbol="AGII", yahoo_ticker="CUSTOM.JK")
        self.assertIs(_research_mappings([explicit])["AGII"], explicit)

    def test_existing_research_fallbacks_remain_unchanged(self):
        available = _research_mappings([])
        self.assertEqual(available["MPMX"].yahoo_ticker, "MPMX.JK")
        self.assertEqual(available["BDMN"].yahoo_ticker, "BDMN.JK")


if __name__ == "__main__":
    unittest.main()
