import unittest
from unittest.mock import Mock
from datetime import datetime, timedelta, timezone

import pandas as pd

from hanz_app.research.g1_fast_recovery import evaluate_bars, validated_bar, recover_missing_five_minute_bars


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


    def test_5m_fallback_recovers_only_missing_1m_symbols(self):
        engine = Mock()
        frame = pd.DataFrame(
            [{"Open": 100, "High": 105, "Low": 98, "Close": 103, "Volume": 10}],
            index=pd.DatetimeIndex([self.now - timedelta(minutes=5)]),
        )
        engine._cached_market_frame.side_effect = (
            lambda ticker, interval, period: {"frame": frame} if ticker == "B" else None
        )
        original = self.now - timedelta(minutes=1)
        bars = recover_missing_five_minute_bars(
            engine, ["A", "B", "C"], {"A": original}, now=self.now
        )
        self.assertEqual(bars, {"A": original, "B": self.now - timedelta(minutes=5)})
        engine.prefetch_market_data.assert_called_once_with(["B", "C"], "5m", "5d")

    def test_5m_fallback_does_not_refetch_when_complete(self):
        engine = Mock()
        bars = {"A": self.fresh}
        self.assertEqual(recover_missing_five_minute_bars(engine, ["A"], bars, now=self.now), bars)
        engine.prefetch_market_data.assert_not_called()

    def test_5m_fallback_rejects_invalid_ohlcv(self):
        engine = Mock()
        frame = pd.DataFrame(
            [{"Open": 100, "High": 99, "Low": 98, "Close": 103, "Volume": 10}],
            index=pd.DatetimeIndex([self.fresh]),
        )
        engine._cached_market_frame.return_value = {"frame": frame}
        self.assertEqual(recover_missing_five_minute_bars(engine, ["A"], {}), {})

    def test_5m_fallback_old_bar_stays_stale(self):
        engine = Mock()
        frame = pd.DataFrame(
            [{"Open": 100, "High": 105, "Low": 98, "Close": 103, "Volume": 10}],
            index=pd.DatetimeIndex([self.now - timedelta(hours=2)]),
        )
        engine._cached_market_frame.return_value = {"frame": frame}
        bars = recover_missing_five_minute_bars(engine, self.symbols, {})
        self.assertEqual(evaluate_bars(self.symbols, bars, self.now)["status"], "STALE")


    def test_5m_fallback_retries_stale_but_valid_1m_bar(self):
        engine = Mock()
        old = self.now - timedelta(hours=2)
        fresh_5m = self.now - timedelta(minutes=5)
        frame = pd.DataFrame(
            [{"Open": 100, "High": 105, "Low": 98, "Close": 103, "Volume": 10}],
            index=pd.DatetimeIndex([fresh_5m]),
        )
        engine._cached_market_frame.return_value = {"frame": frame}
        bars = recover_missing_five_minute_bars(
            engine, ["A"], {"A": old}, now=self.now
        )
        self.assertEqual(bars["A"], fresh_5m)
        engine.prefetch_market_data.assert_called_once_with(["A"], "5m", "5d")

    def test_5m_fallback_never_overwrites_newer_1m_with_older_5m(self):
        engine = Mock()
        old_1m = self.now - timedelta(hours=2)
        older_5m = old_1m - timedelta(minutes=5)
        frame = pd.DataFrame(
            [{"Open": 100, "High": 105, "Low": 98, "Close": 103, "Volume": 10}],
            index=pd.DatetimeIndex([older_5m]),
        )
        engine._cached_market_frame.return_value = {"frame": frame}
        bars = recover_missing_five_minute_bars(
            engine, ["A"], {"A": old_1m}, now=self.now
        )
        self.assertEqual(bars["A"], old_1m)

    def test_5m_fallback_retries_out_of_session_1m_bar(self):
        engine = Mock()
        preopen = datetime(2026, 10, 27, 0, 30, tzinfo=timezone.utc)
        fresh_5m = self.now - timedelta(minutes=5)
        frame = pd.DataFrame(
            [{"Open": 100, "High": 105, "Low": 98, "Close": 103, "Volume": 10}],
            index=pd.DatetimeIndex([fresh_5m]),
        )
        engine._cached_market_frame.return_value = {"frame": frame}
        bars = recover_missing_five_minute_bars(
            engine, ["A"], {"A": preopen}, now=self.now
        )
        self.assertEqual(bars["A"], fresh_5m)

    def test_5m_fallback_rejects_naive_verification_time(self):
        with self.assertRaises(ValueError):
            recover_missing_five_minute_bars(
                Mock(), ["A"], {}, now=self.now.replace(tzinfo=None)
            )



if __name__ == "__main__":
    unittest.main()
