from bootstrap import PROJECT_ROOT  # noqa: F401
import unittest
from hanz_app.market_data_router import _compare


class IndependentOHLCVTests(unittest.TestCase):
    def setUp(self):
        self.primary = {"date": "2026-10-21", "open": 100, "high": 110, "low": 95, "close": 105, "volume": 1000}

    def test_matching_valid_bars_verify(self):
        result = _compare(self.primary, dict(self.primary))
        self.assertTrue(result["verified"])
        self.assertEqual(result["status"], "VERIFIED")

    def test_missing_verifier_close_cannot_verify(self):
        verifier = dict(self.primary)
        verifier.pop("close")
        self.assertFalse(_compare(self.primary, verifier)["verified"])

    def test_invalid_primary_ohlc_cannot_verify(self):
        primary = dict(self.primary, high=99)
        self.assertFalse(_compare(primary, dict(primary))["verified"])

    def test_zero_volume_cannot_verify(self):
        verifier = dict(self.primary, volume=0)
        self.assertFalse(_compare(self.primary, verifier)["verified"])

    def test_nonfinite_close_cannot_verify(self):
        verifier = dict(self.primary, close=float("nan"))
        self.assertFalse(_compare(self.primary, verifier)["verified"])


if __name__ == "__main__":
    unittest.main()
