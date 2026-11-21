"""Regression: a single immutable monitor read feeds both Top 5 and fallback."""
import unittest
from unittest.mock import patch

from hanz_app.research import generate_top5_5y_backtest as backtest


class G2FrozenMonitorSnapshotTests(unittest.TestCase):
    def test_primary_and_replacement_share_snapshot(self):
        rows = [
            {"ticker": "AAA", "risk_validation": {"canonical_rank_score": 90}},
            {"ticker": "BBB", "risk_validation": {"canonical_rank_score": 80}},
            {"ticker": "CCC", "risk_validation": {"canonical_rank_score": 70}},
            {"ticker": "DDD", "risk_validation": {"canonical_rank_score": 60}},
            {"ticker": "EEE", "risk_validation": {"canonical_rank_score": 50}},
            {"ticker": "FFF", "risk_validation": {"canonical_rank_score": 40}},
        ]
        with patch.object(backtest, "_get_monitor_rows", side_effect=AssertionError("unexpected second fetch")), \
             patch.object(backtest, "_eligible", return_value=True), \
             patch.object(backtest, "_rank", side_effect=lambda r: r["risk_validation"]["canonical_rank_score"]):
            primary = backtest._top5_symbols(rows)
            candidates = backtest._research_candidates(primary, rows)
        self.assertEqual(primary, ["AAA", "BBB", "CCC", "DDD", "EEE"])
        self.assertEqual(candidates, primary + ["FFF"])
        self.assertEqual(len(candidates), len(set(candidates)))

    def test_newest_exclusion_not_resurrected_in_fallback(self):
        rows = [
            {"ticker": "AAA", "rank": 1, "eligible": False},
            {"ticker": "AAA", "rank": 99, "eligible": True},
            {"ticker": "BBB", "rank": 80, "eligible": True},
        ]
        with patch.object(backtest, "_get_monitor_rows", side_effect=AssertionError("unexpected fetch")), \
             patch.object(backtest, "_eligible", side_effect=lambda r: r["eligible"]), \
             patch.object(backtest, "_rank", side_effect=lambda r: r["rank"]):
            primary = backtest._top5_symbols(rows)
            candidates = backtest._research_candidates(primary, rows)
        self.assertEqual(primary, ["BBB"])
        self.assertEqual(candidates, ["BBB"])


if __name__ == "__main__":
    unittest.main()
