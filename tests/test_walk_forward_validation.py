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


class FiveYearEvidenceGateTests(unittest.TestCase):
    def _validator_module(self):
        import importlib.util

        path = PROJECT_ROOT / "src" / "hanz_app" / "research" / "hanz_walk_forward_evidence_validator.py"
        spec = importlib.util.spec_from_file_location("hanz_wfa_evidence_validator", path)
        module = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(module)
        return module

    def test_research_validator_rejects_less_than_five_years(self) -> None:
        import pandas as pd

        module = self._validator_module()
        trades = pd.DataFrame({
            "window_id": [1] * 30,
            "trade_id": list(range(30)),
            "r_multiple": [0.2] * 30,
            "is_oos": [True] * 30,
            "trade_date": pd.date_range("2022-01-01", periods=30, freq="30D"),
        })
        windows = pd.DataFrame({
            "window_id": [1, 2],
            "oos_profit_r": [1.0, 1.0],
            "is_profit_r": [1.0, 1.0],
            "is_years": [1.0, 1.0],
            "oos_years": [0.5, 0.5],
            "window_start": ["2022-01-01", "2023-01-01"],
            "window_end": ["2023-01-01", "2024-12-31"],
        })
        result = module.validate(trades, windows, 95.0)
        self.assertFalse(result["checks"]["five_year_history"])
        self.assertFalse(result["passed"])

    def test_research_validator_accepts_five_year_span_when_other_checks_pass(self) -> None:
        import pandas as pd

        module = self._validator_module()
        trades = pd.DataFrame({
            "window_id": [1] * 40,
            "trade_id": list(range(40)),
            "r_multiple": [0.2] * 40,
            "is_oos": [True] * 40,
            "trade_date": pd.date_range("2021-01-01", periods=40, freq="45D"),
        })
        windows = pd.DataFrame({
            "window_id": [1, 2, 3],
            "oos_profit_r": [2.0, 2.0, 2.0],
            "is_profit_r": [2.0, 2.0, 2.0],
            "is_years": [1.0, 1.0, 1.0],
            "oos_years": [1.0, 1.0, 1.0],
            "window_start": ["2021-01-01", "2022-09-01", "2024-05-01"],
            "window_end": ["2022-08-31", "2024-04-30", "2026-01-02"],
        })
        result = module.validate(trades, windows, 95.0)
        self.assertTrue(result["checks"]["five_year_history"])
        self.assertTrue(result["passed"])


if __name__ == "__main__":
    unittest.main()
