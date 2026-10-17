import pathlib
import unittest


class IndexGateOrderTest(unittest.TestCase):
    def test_market_closed_checked_before_missing_quote(self):
        html = pathlib.Path('docs/dashboard/swing/index.html').read_text(encoding='utf-8')
        gate = html.split('function hanzIndexFreshness(', 1)[1].split('async function hanzLoadIndexObservation', 1)[0]
        self.assertLess(gate.index('const market=idxStatusNow()'), gate.index('if(!raw) return "PRICE_UNVERIFIED"'))
        self.assertLess(gate.index('return "MARKET_NOT_TRADING"'), gate.index('if(!raw) return "PRICE_UNVERIFIED"'))


if __name__ == '__main__':
    unittest.main()
