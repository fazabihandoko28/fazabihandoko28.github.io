import datetime as dt
import io
import json
import os
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch
from hanz_app import autonomous_watchdog as watchdog

class WatchdogTest(unittest.TestCase):
    def check_rows(self, rows):
        class Clock(dt.datetime):
            @classmethod
            def now(cls, tz=None):
                return cls(2026, 10, 12, 6, 42, tzinfo=dt.timezone.utc)
        with patch.object(watchdog.dt, 'datetime', Clock), patch.object(watchdog, 'request', side_effect=lambda url, headers: ([{'daily_bar_at':'2026-10-09'}] * 5 if 'hanz_swing_signal_monitor' in url else rows)), patch.dict(os.environ, {'SUPABASE_URL':'https://example.com', 'SUPABASE_SECRET_KEY':'test'}, clear=True), redirect_stdout(io.StringIO()) as output:
            watchdog.main()
        return json.loads(output.getvalue().splitlines()[0])

    def rows(self):
        return [{'rank':i+1,'ticker':f'T{i}', 'prediction_label':'RADAR_CANDIDATE','source_bar_at':'2026-10-09T00:00:00Z','generated_at':'2026-10-12T06:40:00Z'} for i in range(5)]

    def test_fresh_complete_ranking(self):
        self.assertFalse(self.check_rows(self.rows())['recovery_needed'])

    def test_one_stale_row_requires_recovery(self):
        rows=self.rows(); rows[0]['source_bar_at']='2026-10-08T00:00:00Z'
        self.assertTrue(self.check_rows(rows)['recovery_needed'])

    def test_incomplete_ranking_requires_recovery(self):
        result=self.check_rows(self.rows()[:4])
        self.assertIn('PMR80_INVALID_RANKING',result['issues'])
        self.assertTrue(result['recovery_needed'])
