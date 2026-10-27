import unittest
from datetime import datetime, timedelta, timezone

import pandas as pd

from hanz_app.research.g1_fast_recovery import evaluate_bars, validated_bar


class G1IndependentFastRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 27, 3, 30, tzinfo=timezone.utc)
        self.symbols = [f"T{i:03d}" for i in range(198)]
        self.fresh = self.now - timedelta(minutes=2)

    def test_190_genuine_fresh_bars_are_live(self):
        bars = {s: self.fresh for s in self.symbols[:190]}
        result = evaluate_bars(self.symbols, bars, self.now)
        self.assertEqual(result["status"], "LIVE")
        self.assertEqual(result["fresh_valid_count"], 190)
        self.assertFalse(result["g1_closed"])
        self.assertFalse(result["g0_touched"])

    def test_189_fresh_bars_are_stale(self):
        bars = {s: self.fresh for s in self.symbols[:189]}
        self.assertEqual(evaluate_bars(self.symbols, bars, self.now)["status"], "STALE")

    def test_stale_bars_do_not_count_as_fresh(self):
        bars = {s: self.now - timedelta(hours=2) for s in self.symbols}
        self.assertEqual(evaluate_bars(self.symbols, bars, self.now)["fresh_valid_count"], 0)

    def test_future_bars_do_not_count(self):
        bars = {s: self.now + timedelta(seconds=1) for s in self.symbols}
        self.assertEqual(evaluate_bars(self.symbols, bars, self.now)["status"], "STALE")

    def test_wrong_universe_size_fails_closed(self):
        bars = {s: self.fresh for s in self.symbols}
        self.assertEqual(evaluate_bars(self.symbols[:190], bars, self.now)["status"], "STALE")

    def test_closed_session_never_live(self):
        sunday = datetime(2026, 10, 25, 3, 30, tzinfo=timezone.utc)
        bars = {s: sunday - timedelta(minutes=2) for s in self.symbols}
        self.assertEqual(evaluate_bars(self.symbols, bars, sunday)["status"], "STALE")

    def test_last_bar_ohlcv_is_validated(self):
        frame = pd.DataFrame([{"Open": 100, "High": 105, "Low": 98, "Close": 103, "Volume": 10}], index=pd.DatetimeIndex([self.fresh]))
        self.assertEqual(validated_bar(frame), self.fresh)
        frame.loc[self.fresh, "High"] = 99
        self.assertIsNone(validated_bar(frame))

    def test_naive_and_missing_volume_rejected(self):
        frame = pd.DataFrame([{"Open": 100, "High": 105, "Low": 98, "Close": 103, "Volume": 10}], index=pd.DatetimeIndex([self.fresh.replace(tzinfo=None)]))
        self.assertIsNone(validated_bar(frame))
        frame.index = pd.DatetimeIndex([self.fresh])
        frame.drop(columns=["Volume"], inplace=True)
        self.assertIsNone(validated_bar(frame))


if __name__ == "__main__":
    unittest.main()
