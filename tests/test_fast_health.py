import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pandas as pd
from hanz_app import fast_trading_engine as engine


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


if __name__ == "__main__":
    unittest.main()
