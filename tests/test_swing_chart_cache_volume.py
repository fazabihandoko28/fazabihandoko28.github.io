"""Regression tests for fail-closed swing chart cache freshness."""
import unittest
from datetime import date
from unittest.mock import patch

import pandas as pd

from hanz_app import swing_trading_engine as engine


class SwingChartCacheVolumeTests(unittest.TestCase):
    def frame(self, last_volume):
        index = pd.bdate_range(end="2026-10-20", periods=60)
        return pd.DataFrame(
            {"Open": [100.0] * 60, "High": [101.0] * 60,
             "Low": [99.0] * 60, "Close": [100.0] * 60,
             "Volume": [1000] * 59 + [last_volume]},
            index=index,
        )

    def freshness(self):
        return {"target_date": "2026-10-20", "source": "DAILY",
                "repaired": False}

    def test_zero_volume_last_bar_never_written_as_fresh(self):
        frame = self.frame(0)
        with patch.object(engine, "ensure_latest_completed_daily_bar",
                          return_value=(frame, self.freshness())), \
             patch.object(engine, "supabase_request") as write:
            with self.assertRaisesRegex(RuntimeError, "no traded volume"):
                engine.upsert_chart_data("ADCP", frame, {"state": "SWING_BUY"})
            write.assert_not_called()

    def test_positive_volume_last_bar_can_be_cached(self):
        frame = self.frame(1200)
        with patch.object(engine, "ensure_latest_completed_daily_bar",
                          return_value=(frame, self.freshness())), \
             patch.object(engine, "supabase_request") as write:
            result = engine.upsert_chart_data(
                "BBCA", frame, {"state": "SWING_BUY"})
            self.assertTrue(result["stored"])
            self.assertEqual(result["source_bar_at"], "2026-10-20")
            self.assertEqual(write.call_count, 1)

    def test_fresh_cache_timestamp_does_not_hide_stale_monitor(self):
        monitor = [{"ticker": "ADCP", "state": "SWING_BUY",
                    "daily_bar_at": "2026-10-09T00:00:00Z"}]
        cache = [{"ticker": "ADCP", "source_bar_at": "2026-10-20"}]
        with patch.object(engine, "supabase_request",
                          side_effect=[monitor, cache]), \
             patch.object(engine, "latest_completed_idx_date",
                          return_value=date(2026, 10, 20)), \
             patch.object(engine, "download_frame", return_value=object()) as download, \
             patch.object(engine, "upsert_chart_data",
                          return_value={"stored": False}):
            summary = engine.backfill_active_chart_cache()
            self.assertEqual(summary["already_current"], 0)
            download.assert_called_once()
            self.assertEqual(summary["failed"], 0)


if __name__ == "__main__":
    unittest.main()
