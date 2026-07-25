import unittest

from hanz_data.providers.source_policy import require_live_trade_source, require_paper_trade_source


class SourcePolicyTests(unittest.TestCase):
    def test_yahoo_allowed_for_paper_only(self):
        policy = require_paper_trade_source("YAHOO_FINANCE_RESEARCH_ONLY")
        self.assertTrue(policy.allowed_for_paper_trade)
        self.assertFalse(policy.allowed_for_live_trade)
        with self.assertRaises(ValueError):
            require_live_trade_source("YAHOO_FINANCE_RESEARCH_ONLY")


if __name__ == "__main__":
    unittest.main()
