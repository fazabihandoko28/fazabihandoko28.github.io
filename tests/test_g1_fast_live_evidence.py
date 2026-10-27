import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from hanz_app.research.g1_fast_live_evidence import evaluate, session_open


class G1FastLiveEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 26, 3, 30, tzinfo=timezone.utc)  # Monday 10:30 WIB
        self.good = {
            "data_status": "FRESH", "symbols_monitored": 198,
            "data_age_seconds": 60,
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

    def test_g1_agreed_190_threshold_accepts_fresh_partial_only(self):
        for n in (190, 193, 197):
            with self.subTest(coverage=n):
                row = {**self.good, "symbols_monitored": n, "data_status": "PARTIAL"}
                self.assertTrue(evaluate(row, self.now)["g1_fast_live_verified"])

    def test_below_190_remains_incomplete(self):
        for n in (0, 189):
            with self.subTest(coverage=n):
                row = {**self.good, "symbols_monitored": n, "data_status": "PARTIAL"}
                self.assertIn("g1_coverage_incomplete", evaluate(row, self.now)["blockers"])

    def test_partial_source_with_old_candles_is_stale(self):
        for age in (1801, 27416):
            with self.subTest(age=age):
                row = {**self.good, "symbols_monitored": 193,
                       "data_status": "PARTIAL", "data_age_seconds": age}
                self.assertFalse(evaluate(row, self.now)["g1_fast_live_verified"])

    def test_partial_coverage_mislabeled_fresh_fails_closed(self):
        row = {**self.good, "symbols_monitored": 193, "data_status": "FRESH"}
        report = evaluate(row, self.now)
        self.assertFalse(report["g1_fast_live_verified"])
        self.assertIn("source_status_coverage_conflict", report["blockers"])

    def test_invalid_symbol_counts_cannot_be_coerced_into_g1_live(self):
        # Before the guard, 198.9 and "198" were coerced to 198 and passed.
        for invalid in (198.9, 198.0, "198", True, None):
            with self.subTest(coverage=invalid):
                report = evaluate({**self.good, "symbols_monitored": invalid}, self.now)
                self.assertFalse(report["g1_fast_live_verified"])
                self.assertIn("g1_coverage_incomplete", report["blockers"])
        self.assertTrue(evaluate(self.good, self.now)["g1_fast_live_verified"])

    def test_overreported_coverage_cannot_prove_g1_live(self):
        # Before the guard, a source claiming 199/198 or 1000/198 passed LIVE.
        for invalid in (199, 1000):
            with self.subTest(coverage=invalid):
                report = evaluate({**self.good, "symbols_monitored": invalid}, self.now)
                self.assertFalse(report["g1_fast_live_verified"])
                self.assertEqual(report["g1_fast_live"], "STALE")
                self.assertIn("g1_coverage_invalid", report["blockers"])
        self.assertTrue(evaluate(self.good, self.now)["g1_fast_live_verified"])

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

    def test_bar_after_scan_cannot_be_live(self):
        # Both timestamps are individually fresh, but a completed scan
        # cannot contain a candle from after its recorded completion.
        row = {**self.good, "last_market_bar_at":
               (self.now - timedelta(minutes=2)).isoformat()}
        report = evaluate(row, self.now)
        self.assertFalse(report["g1_fast_live_verified"])
        self.assertIn("bar_after_scan", report["blockers"])

    def test_preopen_and_lunch_bars_cannot_prove_live(self):
        cases = (
            # 09:01 WIB after an 08:59 WIB pre-open bar.
            (datetime(2026, 10, 26, 2, 1, tzinfo=timezone.utc),
             datetime(2026, 10, 26, 1, 59, tzinfo=timezone.utc)),
            # 13:31 WIB after a 13:25 WIB lunch-break bar.
            (datetime(2026, 10, 26, 6, 31, tzinfo=timezone.utc),
             datetime(2026, 10, 26, 6, 25, tzinfo=timezone.utc)),
        )
        for now, bar in cases:
            with self.subTest(now=now, bar=bar):
                row = {
                    **self.good,
                    "last_scan_at": (now - timedelta(seconds=5)).isoformat(),
                    "last_market_bar_at": bar.isoformat(),
                }
                report = evaluate(row, now)
                self.assertFalse(report["g1_fast_live_verified"])
                self.assertIn("bar_outside_idx_regular_session", report["blockers"])

    def test_source_reported_stale_age_cannot_prove_live(self):
        # Reproduced before fix: status FRESH + recent bar/scan + age 7200
        # incorrectly produced LIVE despite the provider's stale-age evidence.
        row = {**self.good, "data_age_seconds": 7200}
        report = evaluate(row, self.now)
        self.assertEqual(report["g1_fast_live"], "STALE")
        self.assertIn("source_reported_age_not_fresh", report["blockers"])

    def test_invalid_or_missing_reported_age_fails_closed(self):
        for age in (None, -1, True, "60", 1801):
            with self.subTest(age=age):
                row = {**self.good, "data_age_seconds": age}
                self.assertFalse(evaluate(row, self.now)["g1_fast_live_verified"])

    def test_reported_age_at_guard_boundary_is_accepted(self):
        # Age is measured when the scan completes; 1500s + 300s = 1800s.
        row = {**self.good, "data_age_seconds": 1500,
               "last_scan_at": (self.now - timedelta(seconds=300)).isoformat(),
               "last_market_bar_at": (self.now - timedelta(seconds=360)).isoformat()}
        self.assertTrue(evaluate(row, self.now)["g1_fast_live_verified"])

    def test_age_at_scan_plus_elapsed_time_must_still_be_fresh(self):
        # Reproduces false LIVE: oldest candle was 20m old at a scan 20m ago.
        # Both values pass the separate 30m guards, but its current age is 40m.
        row = {**self.good, "data_age_seconds": 1200,
               "last_scan_at": (self.now - timedelta(seconds=1200)).isoformat(),
               "last_market_bar_at": (self.now - timedelta(seconds=1260)).isoformat()}
        report = evaluate(row, self.now)
        self.assertFalse(report["g1_fast_live_verified"])
        self.assertEqual(report["g1_fast_live"], "STALE")
        self.assertIn("source_reported_age_not_fresh_now", report["blockers"])

    def test_reported_oldest_age_cannot_contradict_bar_timestamp(self):
        # Reproduced false LIVE: 25m-old bar at verification, scan 2m ago,
        # but source claims oldest candle age was zero at scan completion.
        row = {**self.good, "data_age_seconds": 0,
               "last_scan_at": (self.now - timedelta(minutes=2)).isoformat(),
               "last_market_bar_at": (self.now - timedelta(minutes=25)).isoformat()}
        report = evaluate(row, self.now)
        self.assertEqual(report["g1_fast_live"], "STALE")
        self.assertIn("source_age_conflicts_with_bar_timestamp", report["blockers"])

        # Consistent reported age still passes the original freshness gate.
        row["data_age_seconds"] = 23 * 60
        self.assertTrue(evaluate(row, self.now)["g1_fast_live_verified"])

        # Minute-bar rounding within 60 seconds is not a contradiction.
        row["data_age_seconds"] = 0
        row["last_market_bar_at"] = (self.now - timedelta(minutes=3)).isoformat()
        self.assertTrue(evaluate(row, self.now)["g1_fast_live_verified"])

    def test_source_reported_age_is_visible_in_evidence(self):
        self.assertEqual(evaluate(self.good, self.now)["data_age_seconds"], 60)

    def test_missing_health_row_fails_closed(self):
        self.assertFalse(evaluate({}, self.now)["g1_fast_live_verified"])


if __name__ == "__main__":
    unittest.main()
