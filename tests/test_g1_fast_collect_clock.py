"""G1 collect() must evaluate all provider paths against one UTC instant."""
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from hanz_app.research import g1_fast_recovery as recovery


class G1CollectClockTests(unittest.TestCase):
    def test_single_cycle_clock_for_primary_fallback_and_result(self):
        now = datetime(2026, 11, 16, 3, 30, tzinfo=timezone.utc)
        class Engine:
            _CYCLE_PROVIDER_SUCCESSES = 0
            _CYCLE_PROVIDER_FAILURES = 0
            _CYCLE_MARKET_BARS = {}
            INTRADAY_INTERVAL = "1m"
            INTRADAY_PERIOD = "5d"
            @staticmethod
            def fetch_scout_universe():
                return ["ABMM"]
            @staticmethod
            def fetch_watchlist():
                return []
            @staticmethod
            def supabase_request(*args):
                return []
            @staticmethod
            def clean_ticker(value):
                return value
            @staticmethod
            def prefetch_market_data(*args):
                return None
            @staticmethod
            def _cached_market_frame(*args):
                return {"frame": object()}
        engine = Engine()
        with patch("hanz_app.fast_trading_engine.fetch_scout_universe", engine.fetch_scout_universe), \
             patch("hanz_app.fast_trading_engine.fetch_watchlist", engine.fetch_watchlist), \
             patch("hanz_app.fast_trading_engine.supabase_request", engine.supabase_request), \
             patch("hanz_app.fast_trading_engine._cached_market_frame", engine._cached_market_frame), \
             patch("hanz_app.fast_trading_engine.prefetch_market_data", engine.prefetch_market_data), \
             patch("hanz_app.research.g1_fast_recovery.G1_UNIVERSE_SIZE", 1), \
             patch("hanz_app.research.g1_fast_recovery.session_open", return_value=True), \
             patch("hanz_app.research.g1_fast_recovery.datetime") as clock, \
             patch("hanz_app.research.g1_fast_recovery.validated_bar", return_value=None) as validate, \
             patch("hanz_app.research.g1_fast_recovery.recover_missing_with_fallbacks") as fallback, \
             patch("hanz_app.research.g1_fast_recovery.evaluate_bars", return_value={"status": "STALE"}) as evaluate:
            clock.now.return_value = now
            recovery.collect()
            clock.now.assert_called_once_with(timezone.utc)
            self.assertEqual(validate.call_args.kwargs["now"], now)
            self.assertEqual(fallback.call_args.kwargs["now"], now)
            self.assertEqual(evaluate.call_args.args[2], now)


if __name__ == "__main__":
    unittest.main()
