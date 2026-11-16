"""G1 regression: fallback providers must share a single evidence clock."""
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from hanz_app.research.g1_fast_recovery import recover_missing_with_fallbacks


class G1FallbackSnapshotTests(unittest.TestCase):
    def test_shared_clock_for_both_paths(self):
        now = datetime(2026, 11, 16, 3, 30, tzinfo=timezone.utc)
        bars = {}
        with patch("hanz_app.research.g1_fast_recovery.recover_missing_five_minute_bars") as five, patch(
            "hanz_app.research.g1_fast_recovery.recover_missing_direct_chart"
        ) as direct:
            self.assertIs(recover_missing_with_fallbacks(object(), ["ABMM"], bars, now=now), bars)
            self.assertEqual(five.call_args.kwargs["now"], now)
            self.assertEqual(direct.call_args.kwargs["now"], now)

    def test_five_minute_failure_still_reaches_direct(self):
        now = datetime(2026, 11, 16, 3, 30, tzinfo=timezone.utc)
        diagnostic = {}
        with patch("hanz_app.research.g1_fast_recovery.recover_missing_five_minute_bars",
                   side_effect=RuntimeError("provider unavailable")), patch(
            "hanz_app.research.g1_fast_recovery.recover_missing_direct_chart"
        ) as direct:
            recover_missing_with_fallbacks(object(), ["ABMM"], {}, diagnostic, now=now)
            direct.assert_called_once()
            self.assertEqual(direct.call_args.kwargs["now"], now)
            self.assertEqual(diagnostic["five_minute_fallback_error"], "RuntimeError")

    def test_naive_clock_rejected(self):
        with self.assertRaises(ValueError):
            recover_missing_with_fallbacks(object(), [], {}, now=datetime(2026, 11, 16))


if __name__ == "__main__":
    unittest.main()
