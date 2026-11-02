"""G1 research-only regression for BANK historical provider mapping."""
import unittest

from hanz_data import YahooSymbol
from hanz_app.research.generate_top5_5y_backtest import _research_mappings


class G1BacktestBankMappingTests(unittest.TestCase):
    def test_bank_has_explicit_research_only_yahoo_mapping(self):
        available = _research_mappings([])
        self.assertIn("BANK", available)
        self.assertEqual(available["BANK"].market, "BEI")
        self.assertEqual(available["BANK"].symbol, "BANK")
        self.assertEqual(available["BANK"].yahoo_ticker, "BANK.JK")

    def test_existing_explicit_mapping_takes_precedence(self):
        explicit = YahooSymbol(market="BEI", symbol="BANK", yahoo_ticker="VERIFIED.JK")
        self.assertIs(_research_mappings([explicit])["BANK"], explicit)

    def test_existing_research_fallbacks_unchanged(self):
        available = _research_mappings([])
        self.assertEqual(available["MPMX"].yahoo_ticker, "MPMX.JK")
        self.assertEqual(available["BDMN"].yahoo_ticker, "BDMN.JK")
        self.assertEqual(available["AGII"].yahoo_ticker, "AGII.JK")
        self.assertEqual(available["WIIM"].yahoo_ticker, "WIIM.JK")


if __name__ == "__main__":
    unittest.main()
