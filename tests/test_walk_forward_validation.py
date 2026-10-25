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

    def test_explicit_oos_history_ignores_unassigned_trade_timestamps(self) -> None:
        import pandas as pd

        module = self._validator_module()
        # A stray 2020 OOS trade has no window_id; actual OOS windows span
        # only 2024-2026. It must not manufacture six years of coverage.
        trades = pd.DataFrame({
            "is_oos": [True] * 30,
            "r_multiple": [0.2] * 30,
            "trade_date": ["2020-01-01"] + ["2024-08-01"] * 28 + ["2025-01-01"],
        })
        windows = pd.DataFrame({
            "window_id": ["W1", "W2"],
            "oos_profit_r": [1.0, 1.0],
            "oos_start": ["2024-01-01", "2025-01-01"],
            "oos_end": ["2025-01-01", "2026-01-01"],
        })
        result = module.validate(trades, windows, 95.0)
        self.assertFalse(result["checks"]["five_year_history"])
        self.assertLess(result["backtest_years"], 5.0)

        # Even excluded trade dates must still pass chronology validation.
        invalid = trades.copy()
        invalid.loc[0, "trade_date"] = "invalid-date"
        with self.assertRaisesRegex(ValueError, r"Invalid .*chronology.*trade_date"):
            module.validate(invalid, windows, 95.0)

        # Five genuine OOS years still count, and legacy exports retain
        # trade-date evidence when explicit OOS bounds are absent.
        extended = windows.copy()
        extended.loc[0, "oos_start"] = "2020-01-01"
        self.assertTrue(module.validate(trades, extended, 95.0)["checks"]["five_year_history"])
        legacy = windows.drop(columns=["oos_start", "oos_end"])
        self.assertTrue(module.validate(trades, legacy, 95.0)["checks"]["five_year_history"])

    def test_research_rejects_oos_outside_enclosing_window(self) -> None:
        import pandas as pd

        module = self._validator_module()
        trades = pd.DataFrame({
            "is_oos": [True] * 30,
            "r_multiple": [0.2] * 30,
        })
        windows = pd.DataFrame({
            "window_id": ["W1", "W2"],
            "oos_profit_r": [1.0, 1.0],
            "window_start": ["2024-01-01", "2025-01-01"],
            "window_end": ["2025-01-01", "2026-01-01"],
            "oos_start": ["2020-01-01", "2025-01-01"],
            "oos_end": ["2021-01-01", "2026-01-01"],
        })
        # Previously false 6Y OOS coverage was accepted despite W1
        # claiming a test interval outside its enclosing WFA window.
        with self.assertRaisesRegex(ValueError, "outside enclosing window"):
            module.validate(trades, windows, 95.0)

        windows.loc[0, "window_start"] = "2020-01-01"
        windows.loc[0, "window_end"] = "2022-01-01"
        self.assertTrue(module.validate(trades, windows, 95.0)["checks"]["five_year_history"])

    def test_research_rejects_reversed_oos_bounds_without_trade_dates(self) -> None:
        import pandas as pd

        module = self._validator_module()
        trades = pd.DataFrame({
            "is_oos": [True] * 30,
            "r_multiple": [0.2] * 30,
        })
        windows = pd.DataFrame({
            "window_id": ["W1", "W2"],
            "oos_profit_r": [1.0, 1.0],
            "oos_start": ["2026-01-01", "2025-01-01"],
            "oos_end": ["2020-01-01", "2024-01-01"],
        })
        # Without dated trade exports, reversed OOS bounds used to fabricate
        # a six-year history span from a backwards 2026 -> 2020 window.
        with self.assertRaisesRegex(ValueError, "reversed OOS boundaries"):
            module.validate(trades, windows, 95.0)

        windows["oos_start"] = ["2020-01-01", "2024-01-01"]
        windows["oos_end"] = ["2021-01-01", "2026-01-01"]
        self.assertTrue(module.validate(trades, windows, 95.0)["checks"]["five_year_history"])

    def test_explicit_oos_bounds_exclude_is_window_history_from_five_year_gate(self) -> None:
        import pandas as pd

        module = self._validator_module()
        # IS begins in 2020 but independently tested OOS starts only in 2024.
        trades = pd.DataFrame({
            "is_oos": [True] * 30,
            "r_multiple": [0.2] * 30,
            "trade_date": pd.date_range("2024-01-01", periods=30, freq="25D"),
        })
        windows = pd.DataFrame({
            "window_id": ["W1", "W2", "W3"],
            "oos_profit_r": [2.0] * 3,
            "is_profit_r": [2.0] * 3,
            "is_years": [1.0] * 3,
            "oos_years": [1.0] * 3,
            "window_start": ["2020-01-01", "2021-01-01", "2022-01-01"],
            "window_end": ["2026-01-01"] * 3,
            "oos_start": ["2024-01-01"] * 3,
            "oos_end": ["2026-01-01"] * 3,
        })
        result = module.validate(trades, windows, 95.0)
        self.assertFalse(result["checks"]["five_year_history"])
        self.assertLess(result["backtest_years"], 5)
        self.assertFalse(result["passed"])

        # Valid five-year OOS bounds must also fit their enclosing windows.
        windows["window_start"] = "2020-01-01"
        windows["oos_start"] = "2020-01-01"
        self.assertTrue(module.validate(trades, windows, 95.0)["checks"]["five_year_history"])

        # Legacy exports without explicit OOS bounds preserve prior behavior.
        legacy = windows.drop(columns=["oos_start", "oos_end"])
        self.assertTrue(module.validate(trades, legacy, 95.0)["checks"]["five_year_history"])

        # Invalid IS chronology must still be rejected, not silently skipped.
        windows.loc[0, "window_start"] = "not-a-date"
        with self.assertRaisesRegex(ValueError, "Invalid walk-forward chronology evidence"):
            module.validate(trades, windows, 95.0)

    def test_research_rejects_corrupt_oos_flags_instead_of_dropping_losses(self) -> None:
        import pandas as pd

        module = self._validator_module()
        valid = pd.DataFrame({
            "is_oos": ["true"] * 30,
            "r_multiple": [0.2] * 30,
            "trade_date": pd.date_range("2020-01-01", periods=30, freq="70D"),
        })
        windows = pd.DataFrame({
            "window_id": [1, 2, 3],
            "oos_profit_r": [2.0, 2.0, 2.0],
            "is_profit_r": [2.0, 2.0, 2.0],
            "is_years": [1.0, 1.0, 1.0],
            "oos_years": [1.0, 1.0, 1.0],
            "window_start": ["2020-01-01", "2022-01-01", "2024-01-01"],
            "window_end": ["2022-01-01", "2024-01-01", "2026-01-02"],
        })
        self.assertTrue(module.validate(valid, windows, 95.0)["passed"])
        # Previously, unknown flags silently excluded 30 losing OOS trades,
        # leaving only winners and allowing a false strategy PASS.
        corrupted = pd.concat([
            valid,
            pd.DataFrame({
                "is_oos": ["tru"] * 30,
                "r_multiple": [-1.0] * 30,
                "trade_date": pd.date_range("2020-01-02", periods=30, freq="70D"),
            }),
        ], ignore_index=True)
        with self.assertRaisesRegex(ValueError, "Invalid OOS/IS trade classification evidence"):
            module.validate(corrupted, windows, 95.0)
        corrupted.loc[30, "is_oos"] = None
        with self.assertRaisesRegex(ValueError, "Invalid OOS/IS trade classification evidence"):
            module.validate(corrupted, windows, 95.0)
        valid.loc[0, "is_oos"] = " YES "
        valid.loc[1, "is_oos"] = " True "
        self.assertTrue(module.validate(valid, windows, 95.0)["passed"])
        is_row = pd.DataFrame({"is_oos": ["False"], "r_multiple": [-10.0],
                               "trade_date": ["2024-01-01"]})
        self.assertEqual(module.validate(pd.concat([valid, is_row], ignore_index=True),
                                         windows, 95.0)["oos_trades"], 30)

    def test_research_rejects_duplicate_trade_identity_evidence(self) -> None:
        import pandas as pd

        module = self._validator_module()
        trades = pd.DataFrame({
            "window_id": ["W1", "W1", "W2"],
            "trade_id": ["T1", " T1 ", "T1"],
            "is_oos": [True, True, True],
            "r_multiple": [0.2, 0.2, 0.2],
            "trade_date": ["2020-01-01", "2021-01-01", "2026-01-01"],
        })
        windows = pd.DataFrame({
            "window_id": ["W1", "W2"],
            "oos_profit_r": [1.0, 1.0],
        })
        # The same trade counted twice in one window inflates the OOS sample.
        with self.assertRaisesRegex(ValueError, "Invalid or duplicate walk-forward trade_id"):
            module.validate(trades, windows, 95.0)

        # IDs may legitimately repeat across separate WFA windows.
        trades.loc[1, "trade_id"] = "T2"
        self.assertEqual(module.validate(trades, windows, 95.0)["oos_trades"], 3)

        for invalid in (None, "  "):
            with self.subTest(invalid=invalid):
                corrupted = trades.copy()
                corrupted.loc[1, "trade_id"] = invalid
                with self.assertRaisesRegex(ValueError, "Invalid or duplicate walk-forward trade_id"):
                    module.validate(corrupted, windows, 95.0)

    def test_research_rejects_orphaned_trade_window_evidence(self) -> None:
        import pandas as pd

        module = self._validator_module()
        windows = pd.DataFrame({
            "window_id": ["W1", "W2"],
            "oos_profit_r": [1.0, 1.0],
        })
        trades = pd.DataFrame({
            "window_id": ["W1", "W2"],
            "trade_id": ["T1", "T2"],
            "is_oos": [True, True],
            "r_multiple": [0.2, 0.2],
            "trade_date": ["2020-01-01", "2026-01-01"],
        })
        self.assertEqual(module.validate(trades, windows, 95.0)["oos_trades"], 2)

        # An orphaned trade must not inflate the OOS sample of known windows.
        orphaned = trades.copy()
        orphaned.loc[1, "window_id"] = "W3"
        with self.assertRaisesRegex(ValueError, "Unknown walk-forward trade window_id"):
            module.validate(orphaned, windows, 95.0)
        # The check also applies to legacy exports without trade_id.
        with self.assertRaisesRegex(ValueError, "Unknown walk-forward trade window_id"):
            module.validate(orphaned.drop(columns="trade_id"), windows, 95.0)
        missing = trades.copy()
        missing.loc[1, "window_id"] = None
        with self.assertRaisesRegex(ValueError, "Invalid walk-forward trade window_id"):
            module.validate(missing, windows, 95.0)
        # Exports without trade window_id remain supported.
        self.assertEqual(module.validate(trades.drop(columns="window_id"), windows, 95.0)["oos_trades"], 2)

    def test_research_rejects_oos_trade_outside_assigned_window(self) -> None:
        import pandas as pd

        module = self._validator_module()
        windows = pd.DataFrame({
            "window_id": ["W1", "W2"],
            "oos_profit_r": [0.2, 0.3],
            "oos_start": ["2020-01-01", "2025-01-01"],
            "oos_end": ["2021-01-01", "2026-01-01"],
        })
        trades = pd.DataFrame({
            "window_id": ["W1", "W2"],
            "trade_id": ["T1", "T2"],
            "is_oos": [True, True],
            "r_multiple": [0.2, 0.3],
            "exit_date": ["2020-01-01T10:00:00Z", "2026-01-01T10:00:00Z"],
        })
        # An intraday exit on the OOS end date is valid.
        self.assertEqual(module.validate(trades, windows, 95.0)["oos_trades"], 2)

        misplaced = trades.copy()
        misplaced.loc[1, "window_id"] = "W1"
        with self.assertRaisesRegex(ValueError, "OOS trade outside assigned"):
            module.validate(misplaced, windows, 95.0)

        # IS trades are not OOS evidence and need not fall inside OOS bounds.
        is_trade = misplaced.copy()
        is_trade.loc[1, "is_oos"] = False
        self.assertEqual(module.validate(is_trade, windows, 95.0)["oos_trades"], 1)

        reversed_bounds = windows.copy()
        reversed_bounds.loc[0, "oos_start"] = "2022-01-01"
        with self.assertRaisesRegex(ValueError, "Invalid walk-forward OOS window chronology"):
            module.validate(trades, reversed_bounds, 95.0)

        # Older exports without explicit OOS bounds retain their prior behavior.
        legacy = windows.drop(columns=["oos_start", "oos_end"])
        self.assertEqual(module.validate(trades, legacy, 95.0)["oos_trades"], 2)

    def test_research_rejects_is_origin_entry_as_oos_trade(self) -> None:
        import pandas as pd

        module = self._validator_module()
        windows = pd.DataFrame({
            "window_id": ["W1", "W2"],
            "oos_profit_r": [0.2, 0.3],
            "oos_start": ["2020-01-01", "2025-01-01"],
            "oos_end": ["2021-01-01", "2026-01-01"],
        })
        trades = pd.DataFrame({
            "window_id": ["W1", "W2"],
            "trade_id": ["T1", "T2"],
            "is_oos": [True, True],
            "r_multiple": [0.2, 0.3],
            "entry_date": ["2020-01-01", "2024-12-30"],
            "exit_date": ["2020-01-05", "2025-01-03"],
        })
        # Previously this IS-origin entry passed because only exit_date
        # was checked against the OOS bounds.
        with self.assertRaisesRegex(ValueError, "OOS trade outside assigned"):
            module.validate(trades, windows, 95.0)

        trades.loc[1, "entry_date"] = "2025-01-01"
        self.assertEqual(module.validate(trades, windows, 95.0)["oos_trades"], 2)

        # IS trades are not subject to OOS entry bounds.
        trades.loc[1, "is_oos"] = False
        trades.loc[1, "entry_date"] = "2024-12-30"
        self.assertEqual(module.validate(trades, windows, 95.0)["oos_trades"], 1)

        # Legacy exports with no entry_date retain exit-only validation.
        self.assertEqual(module.validate(trades.drop(columns="entry_date"), windows, 95.0)["oos_trades"], 1)

    def test_research_rejects_duplicate_or_missing_walk_forward_window_ids(self) -> None:
        import pandas as pd

        module = self._validator_module()
        trades = pd.DataFrame({
            "is_oos": [True] * 30,
            "r_multiple": [0.2] * 30,
            "trade_date": pd.date_range("2020-01-01", periods=30, freq="80D"),
        })
        windows = pd.DataFrame({
            "window_id": ["W1", "W2", "W3"],
            "oos_profit_r": [2.0] * 3,
            "is_profit_r": [2.0] * 3,
            "is_years": [1.0] * 3,
            "oos_years": [1.0] * 3,
            "window_start": ["2020-01-01", "2022-01-01", "2024-01-01"],
            "window_end": ["2022-01-01", "2024-01-01", "2026-01-02"],
        })
        self.assertTrue(module.validate(trades, windows, 95.0)["passed"])

        # Previously, repeating one profitable window three times passed the
        # len(windows) > 1 gate and inflated apparent WFA consistency.
        repeated = windows.copy()
        repeated["window_id"] = ["W1", "W1", "W1"]
        with self.assertRaisesRegex(ValueError, "Invalid or duplicate walk-forward window_id"):
            module.validate(trades, repeated, 95.0)

        for bad in (None, "  "):
            with self.subTest(bad=bad):
                invalid = windows.copy()
                invalid.loc[1, "window_id"] = bad
                with self.assertRaisesRegex(ValueError, "Invalid or duplicate walk-forward window_id"):
                    module.validate(trades, invalid, 95.0)

        padded_duplicate = windows.copy()
        padded_duplicate.loc[1, "window_id"] = " W1 "
        with self.assertRaisesRegex(ValueError, "Invalid or duplicate walk-forward window_id"):
            module.validate(trades, padded_duplicate, 95.0)

    def test_research_rejects_nonfinite_or_impossible_dof_evidence(self) -> None:
        import pandas as pd

        module = self._validator_module()
        trades = pd.DataFrame({
            "is_oos": [True] * 30,
            "r_multiple": [0.2] * 30,
            "trade_date": pd.date_range("2020-01-01", periods=30, freq="80D"),
        })
        windows = pd.DataFrame({
            "window_id": [1, 2, 3],
            "oos_profit_r": [2.0] * 3,
            "is_profit_r": [2.0] * 3,
            "is_years": [1.0] * 3,
            "oos_years": [1.0] * 3,
            "window_start": ["2020-01-01", "2022-01-01", "2024-01-01"],
            "window_end": ["2022-01-01", "2024-01-01", "2026-01-02"],
        })
        self.assertTrue(module.validate(trades, windows, 95.0)["passed"])
        self.assertTrue(module.validate(trades, windows, 100.0)["passed"])
        self.assertFalse(module.validate(trades, windows, 89.9)["passed"])
        for invalid in (float("inf"), -float("inf"), float("nan"), 101.0):
            with self.subTest(invalid=invalid):
                with self.assertRaisesRegex(ValueError, "Invalid degrees-of-freedom remaining evidence"):
                    module.validate(trades, windows, invalid)

    def test_research_rejects_corrupt_dates_in_five_year_evidence(self) -> None:
        import pandas as pd

        module = self._validator_module()
        trades = pd.DataFrame({
            "is_oos": [True] * 30,
            "r_multiple": [0.2] * 30,
            "trade_date": pd.date_range("2020-01-01", periods=30, freq="80D"),
        })
        windows = pd.DataFrame({
            "window_id": [1, 2, 3],
            "oos_profit_r": [2.0] * 3,
            "is_profit_r": [2.0] * 3,
            "is_years": [1.0] * 3,
            "oos_years": [1.0] * 3,
            "window_start": ["2020-01-01", "2022-01-01", "2024-01-01"],
            "window_end": ["2022-01-01", "2024-01-01", "2026-01-02"],
        })
        self.assertTrue(module.validate(trades, windows, 95.0)["passed"])
        for bad in (None, "not-a-date"):
            with self.subTest(bad=bad):
                corrupted = windows.copy()
                corrupted.loc[1, "window_start"] = bad
                with self.assertRaisesRegex(ValueError, "Invalid walk-forward chronology evidence: window_start"):
                    module.validate(trades, corrupted, 95.0)

    def test_research_rejects_trade_exit_before_entry(self) -> None:
        import pandas as pd

        module = self._validator_module()
        trades = pd.DataFrame({
            "window_id": ["W1", "W2"],
            "trade_id": ["T1", "T2"],
            "is_oos": [True, True],
            "r_multiple": [0.3, 0.2],
            "entry_date": ["2021-01-01", "2024-01-03"],
            "exit_date": ["2021-01-02", "2024-01-02"],
        })
        windows = pd.DataFrame({
            "window_id": ["W1", "W2"],
            "oos_profit_r": [0.3, 0.2],
        })
        with self.assertRaisesRegex(ValueError, "exit before entry"):
            module.validate(trades, windows, 95.0)
        # Corrected chronology remains a valid input; no safety gate relaxed.
        trades.loc[1, "exit_date"] = "2024-01-04"
        self.assertEqual(module.validate(trades, windows, 95.0)["oos_trades"], 2)

    def test_research_rejects_reversed_walk_forward_window_bounds(self) -> None:
        import pandas as pd

        module = self._validator_module()
        trades = pd.DataFrame({
            "is_oos": [True] * 30,
            "r_multiple": [0.2] * 30,
            "trade_date": pd.date_range("2020-01-01", periods=30, freq="80D"),
        })
        windows = pd.DataFrame({
            "window_id": [1, 2, 3],
            "oos_profit_r": [2.0] * 3,
            "window_start": ["2020-01-01", "2022-01-01", "2024-01-01"],
            "window_end": ["2022-01-01", "2021-12-31", "2026-01-02"],
        })
        with self.assertRaisesRegex(ValueError, "reversed window boundaries"):
            module.validate(trades, windows, 95.0)
        windows.loc[1, "window_end"] = "2024-01-01"
        self.assertTrue(module.validate(trades, windows, 95.0)["checks"]["five_year_history"])

    def test_research_rejects_future_dated_wfa_evidence(self) -> None:
        import pandas as pd

        module = self._validator_module()
        future = (datetime.now(timezone.utc) + timedelta(days=2)).date().isoformat()
        trades = pd.DataFrame({
            "is_oos": [True, True],
            "r_multiple": [0.2, 0.2],
            "trade_date": ["2021-01-01", future],
        })
        windows = pd.DataFrame({
            "window_id": ["W1", "W2"],
            "oos_profit_r": [1.0, 1.0],
        })
        # A future OOS trade must never manufacture a five-year PASS.
        with self.assertRaisesRegex(ValueError, "Future-dated walk-forward chronology evidence: trade_date"):
            module.validate(trades, windows, 95.0)
        # An IS-only future date is also corrupt evidence, not a safe row to skip.
        trades.loc[1, "is_oos"] = False
        with self.assertRaisesRegex(ValueError, "Future-dated walk-forward chronology evidence: trade_date"):
            module.validate(trades, windows, 95.0)
        trades.loc[1, "trade_date"] = "2026-01-01"
        windows["window_start"] = ["2021-01-01", "2023-01-01"]
        windows["window_end"] = ["2023-01-01", future]
        with self.assertRaisesRegex(ValueError, "Future-dated walk-forward chronology evidence: window_end"):
            module.validate(trades, windows, 95.0)
        # Genuine completed historical evidence remains eligible for the 5Y check.
        windows.loc[1, "window_end"] = "2026-01-01"
        self.assertTrue(module.validate(trades, windows, 95.0)["checks"]["five_year_history"])

    def test_research_five_year_calendar_anniversary_including_leap_day(self) -> None:
        import pandas as pd

        module = self._validator_module()
        for start, end, expected in (
            ("2021-01-01", "2026-01-01", True),
            ("2021-01-01", "2025-12-31", False),
            ("2020-02-29", "2025-02-28", True),
            ("2020-02-29", "2025-02-27", False),
        ):
            with self.subTest(start=start, end=end):
                trades = pd.DataFrame({"trade_date": [start, end]})
                years = module._evidence_span_years(trades, pd.DataFrame())
                self.assertIsNotNone(years)
                self.assertEqual(years >= 5.0, expected)
                if expected:
                    self.assertEqual(years, 5.0)

    def test_research_is_trade_cannot_inflate_five_year_oos_span(self) -> None:
        import pandas as pd

        module = self._validator_module()
        trades = pd.DataFrame({
            "is_oos": [True] * 30 + [False],
            "r_multiple": [0.2] * 30 + [-1.0],
            "trade_date": list(pd.date_range("2024-01-01", periods=30, freq="20D")) + ["2020-01-01"],
        })
        windows = pd.DataFrame({
            "window_id": [1, 2, 3],
            "oos_profit_r": [2.0, 2.0, 2.0],
            "is_profit_r": [2.0, 2.0, 2.0],
            "is_years": [1.0, 1.0, 1.0],
            "oos_years": [1.0, 1.0, 1.0],
        })
        # An old IS row is not evidence of five years of OOS trading.
        report = module.validate(trades, windows, 95.0)
        self.assertFalse(report["checks"]["five_year_history"])
        self.assertFalse(report["passed"])
        # Corrupt IS timestamps must still be rejected, not silently filtered.
        corrupted = trades.copy()
        corrupted.loc[30, "trade_date"] = "not-a-date"
        with self.assertRaisesRegex(ValueError, "Invalid walk-forward chronology evidence"):
            module.validate(corrupted, windows, 95.0)
        # A genuine five-year OOS span is still recognized.
        extended = trades.copy()
        extended.loc[0, "trade_date"] = "2020-01-01"
        self.assertTrue(module.validate(extended, windows, 95.0)["checks"]["five_year_history"])

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
            "window_end": ["2022-08-31", "2024-04-30", "2026-01-01"],
        })
        result = module.validate(trades, windows, 95.0)
        self.assertTrue(result["checks"]["five_year_history"])
        self.assertTrue(result["passed"])


    def test_research_rejects_nonfinite_or_missing_oos_trade_returns(self) -> None:
        import pandas as pd

        module = self._validator_module()
        valid = pd.DataFrame({
            "r_multiple": [0.2] * 30,
            "is_oos": [True] * 30,
            "trade_date": pd.date_range("2020-01-01", periods=30, freq="80D"),
        })
        windows = pd.DataFrame({
            "window_id": [1, 2],
            "oos_profit_r": [2.0, 2.0],
        })
        for bad_return in (None, "corrupt", float("nan"), float("inf"), -float("inf")):
            with self.subTest(bad_return=bad_return):
                corrupted = pd.concat([
                    valid,
                    pd.DataFrame({"r_multiple": [bad_return], "is_oos": [True],
                                  "trade_date": ["2026-01-01"]}),
                ], ignore_index=True)
                with self.assertRaisesRegex(ValueError, "Invalid OOS trade return evidence"):
                    module.validate(corrupted, windows, 95.0)

        # Invalid IS trades are not OOS evidence and must not be counted.
        is_only_bad = pd.concat([
            valid,
            pd.DataFrame({"r_multiple": [None], "is_oos": [False],
                          "trade_date": ["2026-01-01"]}),
        ], ignore_index=True)
        self.assertEqual(module.validate(is_only_bad, windows, 95.0)["oos_trades"], 30)

    def test_research_rejects_missing_oos_window_profit_evidence(self) -> None:
        import pandas as pd

        module = self._validator_module()
        trades = pd.DataFrame({
            "window_id": [1] * 30,
            "trade_id": list(range(30)),
            "r_multiple": [0.2] * 30,
            "is_oos": [True] * 30,
            "trade_date": pd.date_range("2020-01-01", periods=30, freq="80D"),
        })
        windows = pd.DataFrame({
            "window_id": [1, 2, 3],
            "oos_profit_r": [2.0, "corrupt", 2.0],
            "is_profit_r": [2.0, 2.0, 2.0],
            "is_years": [1.0, 1.0, 1.0],
            "oos_years": [1.0, 1.0, 1.0],
        })
        with self.assertRaisesRegex(ValueError, "Invalid OOS window profit evidence"):
            module.validate(trades, windows, 95.0)
        windows.loc[1, "oos_profit_r"] = None
        with self.assertRaisesRegex(ValueError, "Invalid OOS window profit evidence"):
            module.validate(trades, windows, 95.0)
        for invalid_profit in (float("inf"), -float("inf")):
            with self.subTest(invalid_profit=invalid_profit):
                windows.loc[1, "oos_profit_r"] = invalid_profit
                with self.assertRaisesRegex(ValueError, "Invalid OOS window profit evidence"):
                    module.validate(trades, windows, 95.0)

    def test_research_rejects_incomplete_wfe_inputs(self) -> None:
        import pandas as pd

        module = self._validator_module()
        trades = pd.DataFrame({
            "r_multiple": [0.2, 0.2],
            "is_oos": [True, True],
            "trade_date": ["2020-01-01", "2026-01-01"],
        })
        valid = pd.DataFrame({
            "window_id": [1, 2],
            "oos_profit_r": [2.0, 2.0],
            "is_profit_r": [2.0, 2.0],
            "is_years": [1.0, 1.0],
            "oos_years": [1.0, 1.0],
        })
        # Pandas sum() previously skipped this missing IS result and
        # produced a misleadingly strong walk-forward efficiency.
        missing_profit = valid.copy()
        missing_profit.loc[1, "is_profit_r"] = None
        with self.assertRaisesRegex(ValueError, "Invalid walk-forward annualization evidence"):
            module.validate(trades, missing_profit, 95.0)
        # A window with no positive test duration cannot be annualized.
        zero_duration = valid.copy()
        zero_duration.loc[1, "oos_years"] = 0.0
        with self.assertRaisesRegex(ValueError, "Invalid walk-forward annualization evidence"):
            module.validate(trades, zero_duration, 95.0)
        infinite_profit = valid.copy()
        infinite_profit.loc[1, "is_profit_r"] = float("inf")
        with self.assertRaisesRegex(ValueError, "Invalid walk-forward annualization evidence"):
            module.validate(trades, infinite_profit, 95.0)
        self.assertIsNotNone(module.validate(trades, valid, 95.0)["wfe"])

    def test_research_drawdown_includes_initial_loss_from_zero_equity(self) -> None:
        import pandas as pd

        module = self._validator_module()
        trades = pd.DataFrame({
            "window_id": [1, 1],
            "trade_id": [1, 2],
            "r_multiple": [-2.0, 0.5],
            "is_oos": [True, True],
            "trade_date": ["2020-01-01", "2026-01-01"],
        })
        windows = pd.DataFrame({
            "window_id": [1, 2],
            "oos_profit_r": [-2.0, 0.5],
        })
        result = module.validate(trades, windows, 95.0)
        self.assertEqual(result["oos_max_dd_r"], 2.0)
        self.assertTrue(result["checks"]["drawdown_measured"])


    def test_research_drawdown_uses_exit_chronology_not_csv_order(self) -> None:
        import pandas as pd

        module = self._validator_module()
        # File order: -2,+3,-2 -> drawdown 2R.
        # Real execution order: +3,-2,-2 -> drawdown 4R.
        trades = pd.DataFrame({
            "window_id": [1, 1, 2],
            "trade_id": [2, 1, 3],
            "r_multiple": [-2.0, 3.0, -2.0],
            "is_oos": [True, True, True],
            "exit_date": ["2024-01-02", "2024-01-01", "2024-01-03"],
        })
        windows = pd.DataFrame({"window_id": [1, 2], "oos_profit_r": [1.0, -2.0]})
        report = module.validate(trades, windows, 95.0)
        self.assertEqual(report["oos_max_dd_r"], 4.0)
        reordered = module.validate(trades.iloc[[1, 0, 2]], windows, 95.0)
        self.assertEqual(reordered["oos_max_dd_r"], 4.0)

    def test_research_drawdown_rejects_invalid_exit_chronology(self) -> None:
        import pandas as pd

        module = self._validator_module()
        trades = pd.DataFrame({
            "window_id": [1], "trade_id": [1], "r_multiple": [-1.0],
            "is_oos": [True], "exit_date": ["not-a-date"],
        })
        windows = pd.DataFrame({"window_id": [1], "oos_profit_r": [-1.0]})
        with self.assertRaisesRegex(ValueError, "Invalid OOS trade chronology"):
            module.validate(trades, windows, 95.0)



class FiveYearSelectionCoverageTests(unittest.TestCase):
    def test_summary_requires_five_full_calendar_years(self) -> None:
        from types import SimpleNamespace
        from hanz_app.research.generate_top5_5y_backtest import _summary

        report = SimpleNamespace(
            events=[], evaluated_events=0, ready_events=0,
            average_ready_forward_return=None,
        )

        def status(start: str, end: str, *, dense: bool = False) -> str:
            first = datetime.fromisoformat(start).replace(tzinfo=timezone.utc)
            last = datetime.fromisoformat(end).replace(tzinfo=timezone.utc)
            count = 1000 if dense else 2
            # Synthetic timestamps are unit-test fixtures, never market evidence.
            bars = [SimpleNamespace(timestamp=first + (last - first) * i / (count - 1))
                    for i in range(count)]
            return _summary("TEST", SimpleNamespace(bars=bars), report)["status"]

        # A roughly 4.9-year backtest used to be incorrectly marked OK.
        self.assertEqual(status("2021-01-01", "2025-12-01"), "LIMITED_HISTORY")
        self.assertEqual(status("2021-01-01", "2026-01-01", dense=True), "OK")
        self.assertEqual(status("2020-02-29", "2025-02-27"), "LIMITED_HISTORY")
        self.assertEqual(status("2020-02-29", "2025-02-28", dense=True), "OK")

    def test_sparse_five_year_candles_never_certify_complete_history(self) -> None:
        from types import SimpleNamespace
        from hanz_app.research.generate_top5_5y_backtest import _summary
        report = SimpleNamespace(events=[], evaluated_events=0, ready_events=0,
                                 average_ready_forward_return=None)
        first = datetime(2021, 1, 1, tzinfo=timezone.utc)
        last = datetime(2026, 1, 1, tzinfo=timezone.utc)
        for count in (2, 999):
            with self.subTest(count=count):
                bars = [SimpleNamespace(timestamp=first + (last - first) * i / (count - 1))
                        for i in range(count)]
                result = _summary("TEST", SimpleNamespace(bars=bars), report)
                self.assertEqual(result["status"], "LIMITED_HISTORY")
                self.assertEqual(result["history_gap_reason"], "INSUFFICIENT_TRADING_SESSIONS")
                self.assertEqual(result["distinct_trading_days"], count)

    def test_long_missing_history_gap_cannot_pass_five_year_coverage(self) -> None:
        from types import SimpleNamespace
        from hanz_app.research.generate_top5_5y_backtest import _summary

        report = SimpleNamespace(events=[], evaluated_events=0, ready_events=0,
                                 average_ready_forward_return=None)
        start = datetime(2020, 1, 1, tzinfo=timezone.utc)
        # 1000 distinct fixture days, followed by a >2-year missing interval
        # and one last bar at the fifth anniversary. Never market evidence.
        bars = [SimpleNamespace(timestamp=start + timedelta(days=i))
                for i in range(1000)]
        bars.append(SimpleNamespace(timestamp=datetime(2025, 1, 2, tzinfo=timezone.utc)))
        result = _summary("TEST", SimpleNamespace(bars=bars), report)
        self.assertEqual(result["distinct_trading_days"], 1001)
        self.assertEqual(result["status"], "LIMITED_HISTORY")
        self.assertEqual(result["history_gap_reason"], "LONG_HISTORY_GAP")
        self.assertGreater(result["max_gap_days"], result["max_allowed_gap_days"])

    def test_dense_five_year_history_has_no_long_gap(self) -> None:
        from types import SimpleNamespace
        from hanz_app.research.generate_top5_5y_backtest import _summary

        report = SimpleNamespace(events=[], evaluated_events=0, ready_events=0,
                                 average_ready_forward_return=None)
        start = datetime(2021, 1, 1, tzinfo=timezone.utc)
        end = datetime(2026, 1, 1, tzinfo=timezone.utc)
        bars = [SimpleNamespace(timestamp=start + (end - start) * i / 999)
                for i in range(1000)]
        result = _summary("TEST", SimpleNamespace(bars=bars), report)
        self.assertEqual(result["status"], "OK")
        self.assertIsNone(result["history_gap_reason"])
        self.assertLessEqual(result["max_gap_days"], result["max_allowed_gap_days"])

    def test_missing_selected_mapping_is_explicit_not_silently_dropped(self) -> None:
        from hanz_app.research.generate_top5_5y_backtest import _selection_coverage

        errors = {}
        coverage = _selection_coverage(
            ["AALI", "BDMN"],
            {"AALI": object()},
            {"AALI": {"status": "OK"}},
            errors,
        )
        self.assertEqual(errors["BDMN"], "MISSING_UNIVERSE_MAPPING")
        self.assertEqual(coverage["selected_count"], 2)
        self.assertEqual(coverage["evaluated_count"], 1)
        self.assertEqual(coverage["unavailable_count"], 1)
        self.assertTrue(coverage["all_selected_accounted_for"])
        self.assertFalse(coverage["backtest_complete"])

    def test_known_yahoo_research_fallbacks_are_mapped_without_fabricating_bars(self) -> None:
        from hanz_app.research.generate_top5_5y_backtest import _research_mappings
        from hanz_data import YahooSymbol

        mappings = _research_mappings([YahooSymbol(market="BEI", symbol="AKRA", yahoo_ticker="AKRA.JK")])
        self.assertEqual(mappings["MPMX"].yahoo_ticker, "MPMX.JK")
        self.assertEqual(mappings["BDMN"].yahoo_ticker, "BDMN.JK")
        self.assertEqual(mappings["AKRA"].yahoo_ticker, "AKRA.JK")
        self.assertNotIn("UNKNOWN", mappings)

    def test_explicit_universe_mapping_takes_precedence_over_research_fallback(self) -> None:
        from hanz_app.research.generate_top5_5y_backtest import _research_mappings
        from hanz_data import YahooSymbol

        configured = YahooSymbol(market="BEI", symbol="MPMX", yahoo_ticker="MPMX.CUSTOM")
        mappings = _research_mappings([configured])
        self.assertIs(mappings["MPMX"], configured)

    def test_limited_history_never_counts_as_completed_five_year_backtest(self) -> None:
        from hanz_app.research.generate_top5_5y_backtest import _selection_coverage

        symbols = ["MPMX", "AKRA", "AMMN", "BDMN", "BTPS"]
        results = {s: {"status": "OK"} for s in symbols}
        results["AMMN"] = {"status": "LIMITED_HISTORY"}
        coverage = _selection_coverage(symbols, {s: object() for s in symbols}, results, {})
        self.assertEqual(coverage["evaluated_count"], 5)
        self.assertEqual(coverage["five_year_history_count"], 4)
        self.assertEqual(coverage["limited_history_symbols"], ["AMMN"])
        self.assertTrue(coverage["all_selected_accounted_for"])
        self.assertFalse(coverage["backtest_complete"])

    def test_empty_selection_cannot_pass_top5_coverage(self) -> None:
        from hanz_app.research.generate_top5_5y_backtest import _selection_coverage

        coverage = _selection_coverage([], {}, {}, {})
        self.assertTrue(coverage["all_selected_accounted_for"])
        self.assertFalse(coverage["backtest_complete"])

    def test_four_full_histories_cannot_pass_top5_coverage(self) -> None:
        from hanz_app.research.generate_top5_5y_backtest import _selection_coverage

        symbols = ["AALI", "AUTO", "BDMN", "BTPS"]
        coverage = _selection_coverage(
            symbols, {s: object() for s in symbols},
            {s: {"status": "OK"} for s in symbols}, {},
        )
        self.assertEqual(coverage["five_year_history_count"], 4)
        self.assertFalse(coverage["backtest_complete"])

    def test_duplicate_ticker_cannot_pass_top5_coverage(self) -> None:
        from hanz_app.research.generate_top5_5y_backtest import _selection_coverage

        symbols = ["AALI", "AUTO", "BDMN", "BTPS", "AALI"]
        coverage = _selection_coverage(
            symbols, {s: object() for s in symbols},
            {s: {"status": "OK"} for s in symbols}, {},
        )
        self.assertEqual(coverage["evaluated_count"], 5)
        self.assertFalse(coverage["backtest_complete"])

    def test_all_five_results_allow_complete_coverage(self) -> None:
        from hanz_app.research.generate_top5_5y_backtest import _selection_coverage

        symbols = ["AALI", "AUTO", "BDMN", "BTPS", "BUKA"]
        errors = {}
        coverage = _selection_coverage(
            symbols, {s: object() for s in symbols},
            {s: {"status": "OK"} for s in symbols}, errors,
        )
        self.assertEqual(errors, {})
        self.assertTrue(coverage["backtest_complete"])
        self.assertEqual(coverage["evaluated_count"], 5)


class FiveYearReplayWindowTests(unittest.TestCase):
    def _series(self, dates):
        from hanz_data import Bar, MarketSeries
        return MarketSeries.from_iterable(
            "AKRA", "BEI", (
                Bar(symbol="AKRA", market="BEI",
                    timestamp=datetime.fromisoformat(day).replace(tzinfo=timezone.utc),
                    open=100, high=101, low=99, close=100, volume=1000)
                for day in dates
            ),
        )

    def test_real_pre_anniversary_sessions_restore_five_calendar_years(self):
        from hanz_app.research.generate_top5_5y_backtest import _five_year_replay_series
        series = self._series(["2019-01-01", "2021-10-18", "2021-10-25", "2026-10-23"])
        replay = _five_year_replay_series(series)
        self.assertEqual([b.timestamp.date().isoformat() for b in replay.bars],
                         ["2021-10-18", "2021-10-25", "2026-10-23"])
        self.assertGreaterEqual(
            replay.bars[-1].timestamp.date(),
            replay.bars[0].timestamp.date().replace(year=2026),
        )

    def test_recent_listing_stays_short_without_fabricated_candles(self):
        from hanz_app.research.generate_top5_5y_backtest import _five_year_replay_series
        short = self._series(["2023-07-07", "2026-10-23"])
        self.assertEqual(_five_year_replay_series(short).bars, short.bars)
        self.assertEqual(_five_year_replay_series(self._series([])).bars, ())

    def test_leap_day_boundary_keeps_real_history(self):
        from hanz_app.research.generate_top5_5y_backtest import _five_year_replay_series
        series = self._series(["2020-02-24", "2020-02-29", "2025-02-28"])
        replay = _five_year_replay_series(series)
        self.assertEqual(replay.bars[0].timestamp.date().isoformat(), "2020-02-24")


if __name__ == "__main__":
    unittest.main()
