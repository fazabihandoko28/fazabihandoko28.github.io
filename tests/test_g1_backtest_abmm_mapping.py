"""ABMM is mapped for G1 research only; never a LIVE or BUY claim."""
import unittest
from hanz_app.research.generate_top5_5y_backtest import _research_mappings


class ABMMResearchMappingTests(unittest.TestCase):
    def test_abmm_has_yahoo_research_mapping(self):
        mapping = _research_mappings([])["ABMM"]
        self.assertEqual(mapping.market, "BEI")
        self.assertEqual(mapping.symbol, "ABMM")
        self.assertEqual(mapping.yahoo_ticker, "ABMM.JK")

    def test_static_mapping_takes_precedence(self):
        from hanz_data import YahooSymbol
        custom = YahooSymbol(market="BEI", symbol="ABMM", yahoo_ticker="CUSTOM.JK")
        self.assertEqual(_research_mappings([custom])["ABMM"].yahoo_ticker, "CUSTOM.JK")


if __name__ == "__main__":
    unittest.main()
