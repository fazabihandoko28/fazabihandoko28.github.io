"""Production diagnostic regression: no fabricated eligibility from duplicate or future rows."""
import unittest
from datetime import datetime, timezone

from hanz_app.research.g2_production_top5 import _candidate_exclusion_diagnostics


AS_OF = datetime(2026, 11, 21, 8, 0, tzinfo=timezone.utc).isoformat()


def signal(ticker, timestamp, action="AVOID", rank=50):
    return {
        "ticker": ticker,
        "updated_at": timestamp,
        "risk_validation": {
            "hanz_action": action,
            "canonical_rank_score": rank,
            "avg_value20": 150_000_000,
            "zero_volume_days20": 0,
            "volatility_status": "NORMAL",
            "momentum_guard": {"blocked": False},
        },
        "entry_low": 100,
        "entry_high": 101,
        "target_1": 105,
    }


class ProductionDiagnosticTests(unittest.TestCase):
    def test_future_snapshot_is_not_counted(self):
        rows = [signal("FUTURE", "2026-11-22T00:00:00Z")]
        result = _candidate_exclusion_diagnostics(rows, as_of=AS_OF)
        self.assertEqual(result["latest_unique_tickers_at_cutoff"], 0)

    def test_newest_snapshot_overrides_older(self):
        rows = [
            signal("TEST", "2026-11-20T10:00:00Z", "AVOID"),
            signal("TEST", "2026-11-19T10:00:00Z", "WAIT"),
        ]
        result = _candidate_exclusion_diagnostics(rows, as_of=AS_OF)
        self.assertEqual(result["latest_unique_tickers_at_cutoff"], 1)
        self.assertEqual(result["exclusion_reason_counts"].get("ACTION_RESTRICTED"), 1)

    def test_market_regime_reason_is_reported_independently_of_action(self):
        row = signal("TEST", "2026-11-20T10:00:00Z", "AVOID")
        row["risk_validation"]["market_regime"] = "RED"
        row["risk_validation"]["market_reason"] = "IHSG weak trend"
        result = _candidate_exclusion_diagnostics([row], as_of=AS_OF)
        self.assertEqual(result["exclusion_reason_counts"]["ACTION_RESTRICTED"], 1)
        self.assertEqual(result["market_regime_counts"], {"RED": 1})
        self.assertEqual(result["red_market_reason_counts"], {"IHSG weak trend": 1})

    def test_age_buckets_expose_stale_market_regime_evidence(self):
        rows = [signal("RECENT", "2026-11-20T10:00:00Z"),
                signal("OLD", "2026-11-17T10:00:00Z")]
        result = _candidate_exclusion_diagnostics(rows, as_of=AS_OF)
        self.assertEqual(result["snapshot_age_bucket_counts"], {"WITHIN_24H": 1, "OLDER_THAN_72H": 1})

    def test_conflicting_market_regime_never_uses_arbitrary_tied_row(self):
        a = signal("TEST", "2026-11-20T10:00:00Z")
        b = signal("TEST", "2026-11-20T10:00:00Z")
        a["risk_validation"]["market_regime"] = "RED"
        b["risk_validation"]["market_regime"] = "GREEN"
        result = _candidate_exclusion_diagnostics([a, b], as_of=AS_OF)
        self.assertEqual(result["market_regime_counts"], {"CONFLICTING_NEWEST_SNAPSHOT": 1})
        self.assertEqual(result["red_market_reason_counts"], {})

    def test_equal_timestamp_conflicting_eligibility_is_reported(self):
        stamp = "2026-11-20T10:00:00Z"
        rows = [signal("TEST", stamp, "AVOID"), signal("TEST", stamp, "WAIT")]
        result = _candidate_exclusion_diagnostics(rows, as_of=AS_OF)
        self.assertEqual(result["exclusion_reason_counts"].get("CONFLICTING_NEWEST_SNAPSHOT"), 1)


if __name__ == "__main__":
    unittest.main()
