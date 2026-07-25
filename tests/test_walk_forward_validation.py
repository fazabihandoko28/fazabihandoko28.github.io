from __future__ import annotations

from bootstrap import PROJECT_ROOT  # noqa: F401

import unittest
from datetime import datetime, timedelta, timezone

from hanz_data import Bar, MarketSeries
from hanz_validation import DecisionOutcome, WalkForwardValidator


def make_series(*, count: int = 100, start: float = 100.0, drift: float = 0.8, volume: float = 20_000_000) -> MarketSeries:
    bars = []
    price = start
    timestamp = datetime(2024, 1, 1, tzinfo=timezone.utc)
    for index in range(count):
        close = price + drift
        bars.append(
            Bar(
                symbol="TEST",
                market="BEI",
                timestamp=timestamp + timedelta(days=index),
                open=price,
                high=close * 1.01,
                low=price * 0.995,
                close=close,
                volume=volume * (2.0 if index % 7 == 0 else 1.0),
            )
        )
        price = close
    return MarketSeries.from_iterable("TEST", "BEI", bars)


class WalkForwardValidatorTests(unittest.TestCase):
    def test_no_lookahead_event_count(self) -> None:
        series = make_series(count=90)
        validator = WalkForwardValidator(minimum_bars=60, horizon_bars=5, step_bars=5)
        report = validator.validate(series)
        self.assertEqual(report.evaluated_events, 6)
        self.assertEqual(len(report.events), 6)
        self.assertEqual(report.events[0].signal_timestamp, series.bars[59].timestamp.isoformat())

    def test_future_path_is_evaluated_after_signal(self) -> None:
        series = make_series(count=80, drift=2.0)
        validator = WalkForwardValidator(
            minimum_bars=60,
            horizon_bars=5,
            step_bars=5,
            target_pct=0.02,
            stop_pct=0.02,
        )
        report = validator.validate(series)
        self.assertTrue(all(event.outcome in set(DecisionOutcome) for event in report.events))
        self.assertTrue(any(event.outcome is DecisionOutcome.TARGET_FIRST for event in report.events))

    def test_insufficient_history_is_rejected(self) -> None:
        validator = WalkForwardValidator(minimum_bars=60, horizon_bars=5)
        with self.assertRaises(ValueError):
            validator.validate(make_series(count=64))

    def test_report_serialization(self) -> None:
        report = WalkForwardValidator(minimum_bars=60, horizon_bars=5, step_bars=10).validate(make_series())
        payload = report.to_dict(include_events=False)
        self.assertIn("status_counts", payload)
        self.assertIn("ready_outcomes", payload)
        self.assertNotIn("events", payload)


if __name__ == "__main__":
    unittest.main()
