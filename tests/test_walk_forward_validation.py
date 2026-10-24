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

        def status(start: str, end: str) -> str:
            bars = [
                SimpleNamespace(timestamp=datetime.fromisoformat(value).replace(tzinfo=timezone.utc))
                for value in (start, end)
            ]
            return _summary("TEST", SimpleNamespace(bars=bars), report)["status"]

        # A roughly 4.9-year backtest used to be incorrectly marked OK.
        self.assertEqual(status("2021-01-01", "2025-12-01"), "LIMITED_HISTORY")
        self.assertEqual(status("2021-01-01", "2026-01-01"), "OK")
        self.assertEqual(status("2020-02-29", "2025-02-27"), "LIMITED_HISTORY")
        self.assertEqual(status("2020-02-29", "2025-02-28"), "OK")

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


if __name__ == "__main__":
    unittest.main()
