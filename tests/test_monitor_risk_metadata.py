"""Regression tests: blocked execution must not leak ENTRY_ZONE via JSON."""
import ast
import pathlib
import unittest

ENGINE = pathlib.Path(__file__).resolve().parents[1] / "src/hanz_app/swing_trading_engine.py"


class MonitorRiskMetadataTests(unittest.TestCase):
    def setUp(self):
        tree = ast.parse(ENGINE.read_text(encoding="utf-8"))
        names = {"sanitize_monitor_risk_validation", "upsert_monitor"}
        nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
        self.assertEqual({n.name for n in nodes}, names)
        self.calls = []
        namespace = {
            "clean_ticker": lambda ticker: ticker,
            "now_iso": lambda: "2026-10-20T16:00:00+00:00",
            "supabase_request": lambda method, path, payload, prefer=None: self.calls.append(payload),
        }
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(ENGINE), "exec"), namespace)
        self.sanitize = namespace["sanitize_monitor_risk_validation"]
        self.upsert = namespace["upsert_monitor"]

    def write_monitor(self, risk_validation):
        daily = {"price": 100, "rsi14": 55, "rvol20": 1.2,
                 "prior_high20": 110, "bar_at": "2026-10-20"}
        weekly = {"rsi14": 53, "bar_at": "2026-10-16"}
        result = {"state": "SETUP_READY", "daily_trend": "UP",
                  "weekly_trend": "UP", "breakout": False, "evidence": []}
        levels = {"entry_status": "ENTRY_ZONE", "entry_note": "technical",
                  "entry_price": 100, "entry_low": 99, "entry_high": 101,
                  "stop_loss": 90, "target_1": 120, "target_2": 130}
        self.upsert("TEST", daily, weekly, result, levels, {}, {}, risk_validation)
        self.assertEqual(len(self.calls), 1)
        return self.calls[0]

    def test_blocked_nested_entry_zone_is_sanitized_without_mutation(self):
        original = {"gate": "BLOCKED", "actionable": False,
                    "entry_status": "ENTRY_ZONE", "entry_note": "stale",
                    "canonical_rank_score": 20}
        result = self.sanitize(original)
        self.assertEqual(result["entry_status"], "UNVALIDATED_LEVELS")
        self.assertFalse(result["actionable"])
        self.assertIn("NO BUY CONFIRMATION", result["entry_note"])
        self.assertEqual(original["entry_status"], "ENTRY_ZONE")

    def test_non_actionable_eligible_gate_is_still_blocked(self):
        result = self.write_monitor({"gate": "ELIGIBLE", "actionable": False,
                                     "entry_status": "ENTRY_ZONE"})
        self.assertEqual(result["entry_status"], "UNVALIDATED_LEVELS")
        self.assertIsNone(result["entry_low"])
        self.assertIsNone(result["target_1"])
        self.assertEqual(result["risk_validation"]["entry_status"], "UNVALIDATED_LEVELS")

    def test_blocked_monitor_clears_both_outer_and_inner_signals(self):
        result = self.write_monitor({"gate": "BLOCKED", "actionable": False,
                                     "entry_status": "ENTRY_ZONE"})
        self.assertEqual(result["entry_status"], "UNVALIDATED_LEVELS")
        self.assertEqual(result["risk_validation"]["entry_status"], "UNVALIDATED_LEVELS")
        self.assertIsNone(result["entry_price"])
        self.assertIsNone(result["stop_loss"])
        self.assertIsNone(result["target_1"])

    def test_eligible_actionable_preserves_validated_levels(self):
        result = self.write_monitor({"gate": "ELIGIBLE", "actionable": True,
                                     "entry_status": "ENTRY_ZONE"})
        self.assertEqual(result["entry_status"], "ENTRY_ZONE")
        self.assertEqual(result["entry_low"], 99)
        self.assertEqual(result["target_1"], 120)
        self.assertEqual(result["risk_validation"]["entry_status"], "ENTRY_ZONE")


if __name__ == "__main__":
    unittest.main()
