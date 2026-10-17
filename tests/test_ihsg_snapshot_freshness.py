import unittest
from datetime import datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pandas as pd

from hanz_app import ihsg_snapshot


WIB = ZoneInfo("Asia/Jakarta")
NOW = datetime(2026, 10, 16, 14, 5, tzinfo=WIB)


class FakeTicker:
    def __init__(self, quote_at):
        self.quote_at = quote_at

    def history(self, *, interval, **kwargs):
        if interval == "1d":
            return pd.DataFrame(
                {"Close": [5800.0, 5863.78]},
                index=pd.DatetimeIndex(
                    [datetime(2026, 10, 15, tzinfo=WIB), datetime(2026, 10, 16, tzinfo=WIB)]
                ),
            )
        return pd.DataFrame(
            {"Close": [5865.0]},
            index=pd.DatetimeIndex([self.quote_at]),
        )


class IhsgSnapshotFreshnessTest(unittest.TestCase):
    def snapshot(self, quote_at, *, live=True):
        state = "SESSION_2" if live else "CLOSED"
        with (
            patch.object(ihsg_snapshot, "jakarta_now", return_value=NOW),
            patch.object(ihsg_snapshot, "idx_market_session", return_value={"state": state, "is_trading_day": True}),
            patch.object(ihsg_snapshot.yf, "Ticker", return_value=FakeTicker(quote_at)),
        ):
            return ihsg_snapshot.fetch_ihsg()

    def test_old_live_quote_is_stale_even_when_snapshot_updated_now(self):
        payload = self.snapshot(NOW - timedelta(hours=2))
        self.assertEqual(payload["quote_type"], "LIVE")
        self.assertTrue(payload["stale"])
        self.assertEqual(payload["updated_at"], NOW.isoformat())

    def test_recent_live_quote_is_fresh(self):
        payload = self.snapshot(NOW - timedelta(minutes=2))
        self.assertFalse(payload["stale"])

    def test_market_closed_last_close_is_not_live_fresh(self):
        payload = self.snapshot(NOW - timedelta(minutes=2), live=False)
        self.assertEqual(payload["quote_type"], "LAST_CLOSE")
        self.assertTrue(payload["stale"])

    def test_future_and_timezone_free_quotes_are_not_fresh(self):
        self.assertFalse(ihsg_snapshot._fresh_live_quote((NOW + timedelta(minutes=1)).isoformat(), NOW, "LIVE", True))
        self.assertFalse(ihsg_snapshot._fresh_live_quote("2026-10-16T14:03:00", NOW, "LIVE", True))
        self.assertFalse(ihsg_snapshot._fresh_live_quote("not-a-time", NOW, "LIVE", True))


if __name__ == "__main__":
    unittest.main()
