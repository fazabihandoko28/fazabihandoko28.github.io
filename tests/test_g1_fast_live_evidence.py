import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from hanz_app.research.g1_fast_live_evidence import evaluate, session_open


class G1FastLiveEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 26, 3, 30, tzinfo=timezone.utc)  # Monday 10:30 WIB
        self.good = {
            "data_status": "FRESH", "symbols_monitored": 198,
            "last_scan_at": (self.now - timedelta(minutes=3)).isoformat(),
            "last_market_bar_at": (self.now - timedelta(minutes=4)).isoformat(),
        }

    def test_fresh_complete_current_session_can_be_live(self):
        self.assertTrue(evaluate(self.good, self.now)["g1_fast_live_verified"])
        self.assertFalse(evaluate(self.good, self.now)["g1_closed"])

    def test_stale_source_never_becomes_live(self):
        row = {**self.good, "data_status": "STALE"}
        report = evaluate(row, self.now)
        self.assertEqual(report["g1_fast_live"], "STALE")
        self.assertIn("source_status_not_fresh", report["blockers"])

    def test_g0_190_threshold_does_not_weaken_g1(self):
        for n in (190, 193, 197):
            with self.subTest(coverage=n):
                self.assertIn("g1_coverage_incomplete", evaluate(
                    {**self.good, "symbols_monitored": n}, self.now)["blockers"])

    def test_old_scan_or_bar_blocks_live_even_if_source_says_fresh(self):
        for key in ("last_scan_at", "last_market_bar_at"):
            with self.subTest(field=key):
                row = {**self.good, key: (self.now - timedelta(hours=2)).isoformat()}
                self.assertFalse(evaluate(row, self.now)["g1_fast_live_verified"])

    def test_future_or_naive_timestamps_block_live(self):
        for invalid in ((self.now + timedelta(seconds=1)).isoformat(),
                        self.now.replace(tzinfo=None).isoformat(), "not-a-date"):
            with self.subTest(invalid=invalid):
                self.assertFalse(evaluate(
                    {**self.good, "last_market_bar_at": invalid}, self.now)["g1_fast_live_verified"])

    def test_weekend_never_reports_live(self):
        sunday = datetime(2026, 10, 25, 3, 24, tzinfo=timezone.utc)
        row = {**self.good, "last_scan_at": sunday.isoformat(),
               "last_market_bar_at": sunday.isoformat()}
        report = evaluate(row, sunday)
        self.assertFalse(report["idx_session_open"])
        self.assertEqual(report["g1_fast_live"], "STALE")

    def test_friday_lunch_and_holiday_do_not_report_live(self):
        self.assertFalse(session_open(datetime(2026, 10, 23, 6, 30, tzinfo=timezone.utc)))
        with patch.dict("os.environ", {"HANZ_IDX_HOLIDAYS": "2026-10-26"}):
            self.assertFalse(session_open(self.now))

    def test_missing_health_row_fails_closed(self):
        self.assertFalse(evaluate({}, self.now)["g1_fast_live_verified"])


if __name__ == "__main__":
    unittest.main()
