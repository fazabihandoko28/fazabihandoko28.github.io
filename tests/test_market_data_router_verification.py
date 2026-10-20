"""Regression: independent IDX verifier cannot PASS with incomplete or invalid OHLC."""
from bootstrap import PROJECT_ROOT  # noqa: F401
import unittest

from hanz_app.market_data_router import _compare


class IndependentOHLCVerificationTests(unittest.TestCase):
    def setUp(self):
        self.bar = {
            "date": "2026-10-20", "open": 100, "high": 105,
            "low": 99, "close": 102, "volume": 10000,
        }

    def test_valid_matching_ohlc_can_verify(self):
        result = _compare(self.bar, dict(self.bar))
        self.assertEqual(result["status"], "VERIFIED")
        self.assertTrue(result["verified"])

    def test_missing_any_verifier_ohlc_cannot_verify(self):
        for key in ("open", "high", "low", "close"):
            with self.subTest(field=key):
                verifier = dict(self.bar)
                verifier.pop(key)
                result = _compare(self.bar, verifier)
                self.assertEqual(result["status"], "UNVERIFIABLE_OHLC")
                self.assertFalse(result["verified"])

    def test_missing_any_primary_ohlc_cannot_verify(self):
        for key in ("open", "high", "low", "close"):
            with self.subTest(field=key):
                primary = dict(self.bar)
                primary.pop(key)
                self.assertFalse(_compare(primary, self.bar)["verified"])

    def test_nonfinite_zero_and_negative_prices_cannot_verify(self):
        for bad_value in (float("nan"), float("inf"), float("-inf"), 0, -1):
            with self.subTest(value=bad_value):
                verifier = dict(self.bar, close=bad_value)
                result = _compare(self.bar, verifier)
                self.assertEqual(result["status"], "UNVERIFIABLE_OHLC")
                self.assertFalse(result["verified"])

    def test_inconsistent_high_low_cannot_verify(self):
        verifier = dict(self.bar, high=100)
        result = _compare(self.bar, verifier)
        self.assertEqual(result["status"], "UNVERIFIABLE_OHLC")
        self.assertFalse(result["verified"])

    def test_mismatched_prices_block(self):
        verifier = dict(self.bar, close=104)
        result = _compare(self.bar, verifier)
        self.assertEqual(result["status"], "MISMATCH")
        self.assertTrue(result["block"])
        self.assertFalse(result["verified"])

    def test_date_mismatch_blocks(self):
        verifier = dict(self.bar, date="2026-10-19")
        self.assertEqual(_compare(self.bar, verifier)["status"], "DATE_MISMATCH")

    def test_no_verifier_is_unverified(self):
        self.assertFalse(_compare(self.bar, None)["verified"])

    def test_volume_mismatch_remains_caution(self):
        verifier = dict(self.bar, volume=100)
        result = _compare(self.bar, verifier)
        self.assertEqual(result["status"], "VERIFIED_PRICE_VOLUME_CAUTION")
        self.assertTrue(result["verified"])


if __name__ == "__main__":
    unittest.main()
