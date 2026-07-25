import tempfile
import unittest
from pathlib import Path

from hanz_data.providers.universe_config import load_yahoo_universe


class UniverseConfigTests(unittest.TestCase):
    def test_disabled_rows_are_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "u.csv"
            path.write_text(
                "market,symbol,yahoo_ticker,enabled\nBEI,BBRI,BBRI.JK,true\nADX,FAB,FAB.AD,false\n",
                encoding="utf-8",
            )
            rows = load_yahoo_universe(path)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].symbol, "BBRI")


if __name__ == "__main__":
    unittest.main()
