"""G2 certification evidence must never silently default to PASS."""
import unittest

from hanz_app.research.g2_certification_gate import REQUIRED, evaluate


class G2CertificationTests(unittest.TestCase):
    def complete(self):
        e = {key: True for key in REQUIRED}
        e.update(selected=["A", "B", "C", "D", "E"], buy_authorized=False,
                 replacement_probe={"verified": True, "removed_ticker": "A", "replacement_ticker": "F",
                                    "reason": "COUNTERFACTUAL_REPLACEMENT_FROM_SAME_SNAPSHOT"})
        return e

    def test_complete_explicit_evidence(self):
        self.assertTrue(evaluate(self.complete())["certified"])

    def test_each_missing_gate_fails_closed(self):
        for key in REQUIRED:
            for value in (None, False, "true", 1):
                with self.subTest(key=key, value=value):
                    e = self.complete()
                    e[key] = value
                    self.assertFalse(evaluate(e)["certified"])

    def test_replacement_must_be_real_and_distinct_top_five(self):
        e = self.complete()
        e["replacement_probe"]["verified"] = "true"
        self.assertFalse(evaluate(e)["certified"])
        e = self.complete()
        e["selected"] = ["A", "B", "C", "D", "D"]
        self.assertFalse(evaluate(e)["certified"])

    def test_replacement_must_remove_selected_and_add_new_ticker(self):
        for removed, entrant in (("Z", "F"), ("A", "A"), ("A", ""), (None, "F")):
            with self.subTest(removed=removed, entrant=entrant):
                e = self.complete()
                e["replacement_probe"]["removed_ticker"] = removed
                e["replacement_probe"]["replacement_ticker"] = entrant
                self.assertFalse(evaluate(e)["certified"])

    def test_buy_authorization_never_implied(self):
        e = self.complete()
        e["buy_authorized"] = True
        self.assertFalse(evaluate(e)["certified"])

    def test_current_production_report_remains_open(self):
        e = {"selected": ["BJTM", "EXCL", "TBIG"],
             "production_top5_complete": False,
             "replacement_probe": {"verified": False}}
        result = evaluate(e)
        self.assertFalse(result["certified"])
        self.assertIn("historical_point_in_time_oos_verified", result["missing"])


if __name__ == "__main__":
    unittest.main()
