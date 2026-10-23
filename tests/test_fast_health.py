import unittest
from unittest.mock import patch as mock_patch
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pandas as pd
from hanz_app import fast_trading_engine as engine
from hanz_app.fast_health_check import same_instant, closed_session_evidence, idx_regular_session_open, complete_universe_coverage, coverage_health_status, runtime_operational_mode


class FastHealthTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 16, 3, tzinfo=timezone.utc)
        self.clock = patch.object(engine, "utc_now", return_value=self.now)
        self.clock.start()
        self.addCleanup(self.clock.stop)
        self.writer = patch.object(engine, "supabase_request")
        self.request = self.writer.start()
        self.addCleanup(self.writer.stop)
        engine._CYCLE_MARKET_BARS.clear()
        self.addCleanup(engine._CYCLE_MARKET_BARS.clear)

    def payload(self, **kwargs):
        engine.update_fast_health(**kwargs)
        return self.request.call_args.args[2]

    def test_idx_regular_sessions_thursday_and_friday(self):
        def utc(day, hour, minute):
            return datetime(2026, 10, day, hour, minute, tzinfo=timezone.utc)
        self.assertTrue(idx_regular_session_open(utc(22, 3, 0)))
        self.assertFalse(idx_regular_session_open(utc(22, 5, 30)))
        self.assertTrue(idx_regular_session_open(utc(22, 7, 0)))
        self.assertFalse(idx_regular_session_open(utc(22, 9, 0)))
        self.assertFalse(idx_regular_session_open(utc(23, 4, 45)))
        self.assertTrue(idx_regular_session_open(utc(23, 7, 0)))
        self.assertFalse(idx_regular_session_open(utc(23, 6, 45)))  # Friday lunch 13:45 WIB
        self.assertTrue(idx_regular_session_open(utc(23, 8, 44)))  # Friday 15:44 WIB
        self.assertFalse(idx_regular_session_open(utc(23, 8, 50)))  # Friday 15:50 WIB
        self.assertTrue(idx_regular_session_open(utc(22, 8, 44)))  # Thursday 15:44 WIB

    def test_idx_configured_holiday_blocks_live_session(self):
        with mock_patch.dict("os.environ", {"HANZ_IDX_HOLIDAYS": "2026-10-22"}):
            self.assertFalse(idx_regular_session_open(
                datetime(2026, 10, 22, 3, tzinfo=timezone.utc)))

    def test_closed_session_evidence_after_idx_close(self):
        # Thursday 20:27 WIB, final-session candle Thursday 15:45 WIB.
        self.assertTrue(closed_session_evidence(
            "2026-10-22T08:45:00+00:00",
            datetime(2026, 10, 22, 13, 27, tzinfo=timezone.utc),
        ))

    def test_closed_session_waits_for_idx_post_close_completion(self):
        friday_bar = "2026-10-23T08:45:00+00:00"  # Friday 15:45 WIB
        for hour, minute in ((8, 44), (9, 10), (9, 15)):
            self.assertFalse(closed_session_evidence(
                friday_bar, datetime(2026, 10, 23, hour, minute, tzinfo=timezone.utc)))
        self.assertTrue(closed_session_evidence(
            friday_bar, datetime(2026, 10, 23, 9, 16, tzinfo=timezone.utc)))
        self.assertFalse(closed_session_evidence(
            "2026-10-23T04:20:00+00:00",
            datetime(2026, 10, 23, 6, 0, tzinfo=timezone.utc)))  # Friday lunch

    def test_closed_session_rejects_morning_and_early_afternoon_candles(self):
        # Production FAST observed 10:18 WIB as oldest candle on Oct 23.
        # Its same-day timestamp must not certify the completed session.
        now = datetime(2026, 10, 23, 13, 37, tzinfo=timezone.utc)
        for bar in ("2026-10-23T03:18:00+00:00",  # 10:18 WIB
                    "2026-10-23T07:55:00+00:00",  # 14:55 WIB
                    "2026-10-23T08:40:00+00:00"):  # 15:40 WIB
            self.assertFalse(closed_session_evidence(bar, now), bar)
        self.assertTrue(closed_session_evidence(
            "2026-10-23T08:45:00+00:00", now))  # 15:45 WIB

    def test_closed_session_never_overrides_live_hours(self):
        self.assertFalse(closed_session_evidence(
            "2026-10-22T03:30:00+00:00",
            datetime(2026, 10, 22, 7, 30, tzinfo=timezone.utc),
        ))

    def test_closed_session_rejects_old_and_future_bars(self):
        now = datetime(2026, 10, 22, 13, 27, tzinfo=timezone.utc)
        for bar in ("2026-10-21T07:55:00+00:00",
                    "2026-10-22T15:00:00+00:00",
                    "2026-10-22T07:55:00", "invalid", None):
            self.assertFalse(closed_session_evidence(bar, now), bar)

    def test_g0_rejects_partial_coverage_even_above_legacy_tolerance(self):
        self.assertFalse(complete_universe_coverage(193, 198, 198))
        self.assertFalse(complete_universe_coverage(198, 200, 198))
        self.assertFalse(complete_universe_coverage(190, 190, 198))
        self.assertTrue(complete_universe_coverage(198, 198, 198))
        self.assertTrue(complete_universe_coverage(200, 200, 198))

    def test_missing_symbols_never_mask_stale_health(self):
        self.assertEqual(coverage_health_status("STALE", False), "STALE")
        self.assertEqual(coverage_health_status("FRESH", False), "PARTIAL")
        self.assertEqual(coverage_health_status("FRESH", True), "FRESH")

    def test_operational_mode_never_labels_stale_candles_live(self):
        self.assertEqual(runtime_operational_mode(False, False), "STALE")
        self.assertEqual(runtime_operational_mode(True, False), "LIVE")
        self.assertEqual(runtime_operational_mode(False, True), "CLOSED_SESSION")
        self.assertEqual(runtime_operational_mode(True, True), "CLOSED_SESSION")

    def test_null_ticker_cannot_inflate_idx_coverage(self):
        self.assertIsNone(engine.normalize_ticker(None))
        for value in (None, "", "  ", "\t"):
            self.assertEqual(engine.clean_ticker(value), "")
        self.assertEqual(engine.clean_ticker(" bbca.jk "), "BBCA")
        self.assertEqual(engine.normalize_ticker(" bbca "), "BBCA.JK")

    def test_fast_readback_accepts_postgres_microsecond_normalization(self):
        # PostgREST drops trailing fractional zeros, even when the same bar was persisted.
        self.assertTrue(same_instant(
            "2026-10-21T12:57:14.207140+00:00",
            "2026-10-21T12:57:14.20714+00:00",
        ))
        self.assertTrue(same_instant(
            "2026-10-21T12:57:14.207140Z",
            "2026-10-21T19:57:14.20714+07:00",
        ))

    def test_fast_readback_still_rejects_wrong_missing_or_naive_evidence(self):
        expected = "2026-10-21T12:57:14.207140+00:00"
        for actual in (
            "2026-10-21T12:57:14.207141+00:00",
            "2026-10-21T12:57:14",
            "invalid",
            None,
        ):
            self.assertFalse(same_instant(expected, actual), actual)

    def test_missing_evidence_never_fresh(self):
        for kwargs in ({}, {"symbols_monitored": 3}, {"last_market_bar_at": self.now.isoformat()}):
            self.assertEqual(self.payload(data_status="FRESH", **kwargs)["data_status"], "STALE")

    def test_invalid_future_naive_and_stale_never_fresh(self):
        for bar in ("invalid", "2026-10-16T03:00:00", (self.now + timedelta(seconds=1)).isoformat(), (self.now - timedelta(days=7)).isoformat()):
            row = self.payload(data_status="FRESH", symbols_monitored=5, last_market_bar_at=bar, data_age_seconds_value=0)
            self.assertEqual(row["data_status"], "STALE", bar)

    def test_verified_recent_bar_is_fresh_and_age_recomputed(self):
        row = self.payload(data_status="FRESH", symbols_monitored=5, last_market_bar_at=(self.now - timedelta(seconds=90)).isoformat(), data_age_seconds_value=0)
        self.assertEqual(row["data_status"], "FRESH")
        self.assertEqual(row["data_age_seconds"], 90)

    def test_provider_degradation_is_preserved(self):
        row = self.payload(data_status="DEGRADED", symbols_monitored=5, last_market_bar_at=self.now.isoformat(), error="provider failures")
        self.assertEqual(row["data_status"], "DEGRADED")
        self.assertEqual(row["last_error"], "provider failures")

    def test_oldest_unique_consumed_bar_drives_health(self):
        engine._CYCLE_MARKET_BARS.update({"BBCA.JK": self.now, "BBRI.JK": self.now - timedelta(days=7)})
        with patch.object(engine, "_provider_cycle_status", return_value="FRESH"), patch.object(engine, "_provider_cycle_error", return_value=None):
            engine.publish_cycle_health()
        row = self.request.call_args.args[2]
        self.assertEqual(row["symbols_monitored"], 2)
        self.assertEqual(row["data_status"], "STALE")
        self.assertEqual(row["data_age_seconds"], 7 * 86400)

    def test_empty_cycle_discards_previous_evidence(self):
        engine._CYCLE_MARKET_BARS["BBCA.JK"] = self.now
        with patch.multiple(engine, fetch_portfolio=lambda: [], fetch_watchlist=lambda: [], FAST_SCOUT_ENABLED=False, cleanup_expired_scout_candidates=lambda: None):
            engine.run_fast_cycle()
        row = self.request.call_args.args[2]
        self.assertEqual(row["symbols_monitored"], 0)
        self.assertEqual(row["data_status"], "STALE")

    def test_cached_frames_supply_evidence_but_confirmation_does_not(self):
        frame = pd.DataFrame({"Close": [100]}, index=pd.DatetimeIndex([self.now]))
        cached = {"frame": frame, "fetched_at": engine.time.time(), "latency": 0}
        with patch.object(engine, "_cached_market_frame", return_value=cached):
            engine.download_data("BBCA", engine.CONFIRM_INTERVAL, engine.CONFIRM_PERIOD)
            self.assertFalse(engine._CYCLE_MARKET_BARS)
            engine.download_data("BBCA", engine.INTRADAY_INTERVAL, engine.INTRADAY_PERIOD)
        self.assertEqual(set(engine._CYCLE_MARKET_BARS), {"BBCA.JK"})

    def test_single_missing_ticker_does_not_open_healthy_feed_circuit(self):
        with patch.multiple(engine, _CYCLE_PROVIDER_SUCCESSES=193, _CYCLE_PROVIDER_FAILURES=5, _PROVIDER_CONSECUTIVE_FAILURES=0, MARKET_FETCH_RETRIES=0, _MARKET_CIRCUIT_OPEN_UNTIL=0), patch.object(engine.yf, "download", return_value=pd.DataFrame()), patch.object(engine, "_open_market_circuit") as trip:
            engine.prefetch_market_data(["MISSING"], "1m", "5d")
        trip.assert_not_called()

    def test_feed_wide_failures_still_open_circuit(self):
        with patch.multiple(engine, _CYCLE_PROVIDER_SUCCESSES=0, _CYCLE_PROVIDER_FAILURES=0, _PROVIDER_CONSECUTIVE_FAILURES=0, MARKET_FETCH_RETRIES=0, _MARKET_CIRCUIT_OPEN_UNTIL=0), patch.object(engine.yf, "download", return_value=pd.DataFrame()), patch.object(engine, "_open_market_circuit") as trip:
            engine.prefetch_market_data(["MISSING"], "1m", "5d")
        trip.assert_called_once()


if __name__ == "__main__":
    unittest.main()
