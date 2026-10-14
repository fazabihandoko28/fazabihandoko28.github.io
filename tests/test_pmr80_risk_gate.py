"""Regression tests for PMR80 candidate and execution gating."""
import unittest
from unittest.mock import patch
from hanz_app import premarket_bullish_predictor as pmr

BAR = "2026-10-13"
FEATURES = {
    "source_date": BAR, "price": 100.0, "ret1_pct": -2.0,
    "ret3_pct": -4.0, "ret5_pct": -6.0, "dist20_pct": -4.0,
    "rvol20": 1.2, "avg_value20": 50_000_000_000.0,
}

class StubEngine:
    def __init__(self, monitor):
        self.monitor = monitor
        self.saved = []
    def supabase_request(self, method, path, payload=None, prefer=None):
        if method == "GET" and "hanz_swing_chart_data" in path:
            return [{"ticker": t, "candles": []} for t in self.monitor]
        if method == "GET" and "hanz_swing_signal_monitor" in path:
            return list(self.monitor.values())
        if method == "POST":
            self.saved = payload
            return []
        raise AssertionError((method, path))
    def now_iso(self):
        return "2026-10-14T06:00:00+00:00"

def monitor_row(ticker, gate="MONITOR", integrity="OK"):
    return {
        "ticker": ticker, "daily_bar_at": BAR, "risk_gate": gate,
        "risk_validation": {"data_integrity_status": integrity},
        "state": "RADAR_WATCH", "entry_status": "ENTRY_ZONE",
        "entry_price": 100.0, "entry_low": 99.0, "entry_high": 101.0,
        "stop_loss": 95.0, "target_1": 105.0, "target_2": 110.0,
    }

class PmrRiskGateTests(unittest.TestCase):
    def run_publish(self, monitor):
        engine = StubEngine(monitor)
        with patch.object(pmr, "_features", return_value=FEATURES), \
             patch.object(pmr, "_strict", return_value=False), \
             patch.object(pmr, "_radar_score", return_value=70):
            summary = pmr.publish(engine)
        return summary, engine.saved

    def test_invalid_ohlc_never_ranked(self):
        monitor = {t: monitor_row(t) for t in ["ANTM", "UNTR", "ARCI", "SSIA", "BBCA"]}
        monitor["DMAS"] = monitor_row("DMAS", "BLOCKED", "INVALID_OHLC")
        summary, rows = self.run_publish(monitor)
        self.assertEqual(summary["published"], 5)
        self.assertNotIn("DMAS", [r["ticker"] for r in rows])

    def test_monitor_and_blocked_have_no_execution_levels(self):
        monitor = {t: monitor_row(t, "BLOCKED" if t == "SSIA" else "MONITOR")
                   for t in ["ANTM", "UNTR", "ARCI", "SSIA", "BBCA"]}
        _, rows = self.run_publish(monitor)
        self.assertEqual(len(rows), 5)
        for row in rows:
            self.assertEqual(row["entry_status"], "UNVALIDATED_LEVELS")
            for key in ("entry_price", "entry_low", "entry_high", "stop_loss", "target_1", "target_2"):
                self.assertIsNone(row[key], key)

    def test_eligible_with_valid_bar_and_stop_retains_levels(self):
        monitor = {t: monitor_row(t) for t in ["ANTM", "UNTR", "ARCI", "SSIA", "BBCA"]}
        monitor["ANTM"] = monitor_row("ANTM", "ELIGIBLE")
        _, rows = self.run_publish(monitor)
        eligible = next(r for r in rows if r["ticker"] == "ANTM")
        self.assertEqual(eligible["entry_status"], "ENTRY_ZONE")
        self.assertEqual(eligible["stop_loss"], 95.0)

    def test_stale_monitor_bar_excluded(self):
        monitor = {t: monitor_row(t) for t in ["ANTM", "UNTR", "ARCI", "SSIA", "BBCA", "BMRI"]}
        monitor["BMRI"]["daily_bar_at"] = "2026-10-09"
        _, rows = self.run_publish(monitor)
        self.assertNotIn("BMRI", [r["ticker"] for r in rows])

if __name__ == "__main__":
    unittest.main()
