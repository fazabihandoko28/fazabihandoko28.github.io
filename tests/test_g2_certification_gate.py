"""G2 certification evidence must never silently default to PASS."""
import unittest

from hanz_app.research.g2_certification_gate import REQUIRED, evaluate


class G2CertificationTests(unittest.TestCase):
    def complete(self):
        e = {key: True for key in REQUIRED}
        e.update(selected=["A", "B", "C", "D", "E"], buy_authorized=False,
                 replacement_probes=[{"verified": True, "removed_ticker": t, "replacement_ticker": "F",
                                    "reason": "COUNTERFACTUAL_REPLACEMENT_FROM_SAME_SNAPSHOT"} for t in ["A", "B", "C", "D", "E"]],
                 replacement_verified_count=5, replacement_probes_complete=True)
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
        e["replacement_probes"][0]["verified"] = "true"
        self.assertFalse(evaluate(e)["certified"])
        e = self.complete()
        e["selected"] = ["A", "B", "C", "D", "D"]
        self.assertFalse(evaluate(e)["certified"])

    def test_replacement_must_remove_selected_and_add_new_ticker(self):
        for removed, entrant in (("Z", "F"), ("A", "A"), ("A", ""), (None, "F")):
            with self.subTest(removed=removed, entrant=entrant):
                e = self.complete()
                e["replacement_probes"][0]["removed_ticker"] = removed
                e["replacement_probes"][0]["replacement_ticker"] = entrant
                self.assertFalse(evaluate(e)["certified"])

    def test_single_leader_probe_cannot_certify_full_replacement(self):
        e = self.complete()
        e["replacement_probes"] = e["replacement_probes"][:1]
        self.assertFalse(evaluate(e)["certified"])

    def test_missing_or_inconsistent_aggregate_fails_closed(self):
        for count, complete in ((1, True), (5, False), (True, True)):
            with self.subTest(count=count, complete=complete):
                e = self.complete()
                e["replacement_verified_count"] = count
                e["replacement_probes_complete"] = complete
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
