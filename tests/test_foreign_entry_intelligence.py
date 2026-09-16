from __future__ import annotations

import unittest
from types import SimpleNamespace

from hanz_app.foreign_entry_intelligence import _absolute_flow_classification, install


class ForeignEntryIntelligenceTests(unittest.TestCase):
    def test_strong_buy_gets_bounded_positive_score(self):
        status, score, _ = _absolute_flow_classification(48_920_000_000)
        self.assertEqual(status, "ACCUMULATING")
        self.assertEqual(score, 12)

    def test_heavy_sell_gets_negative_score(self):
        status, score, _ = _absolute_flow_classification(-146_430_000_000)
        self.assertEqual(status, "DISTRIBUTING")
        self.assertEqual(score, -12)

    def test_adapter_wires_foreign_flow_into_entry_validation(self):
        def base_snapshot(_ticker):
            return {
                "available": True,
                "status": "NEUTRAL",
                "score": 0,
                "net_1d": 48_850_000_000,
                "net_3d": 48_850_000_000,
                "net_5d": 48_850_000_000,
                "net_pct_1d": None,
                "net_pct_3d": None,
                "net_pct_5d": None,
            }

        def base_validation(*_args, **_kwargs):
            return {"score": 40, "cautions": []}

        def apply_flow(rv, ff):
            out = dict(rv)
            out["foreign_flow_status"] = ff.get("status")
            out["foreign_flow_score"] = ff.get("score")
            out["foreign_net_1d"] = ff.get("net_1d")
            out["score"] = int(out.get("score", 0) + ff.get("score", 0))
            return out

        engine = SimpleNamespace(
            foreign_flow_snapshot=base_snapshot,
            real_money_validation=base_validation,
            apply_foreign_flow_to_risk_validation=apply_flow,
        )

        install(engine)
        rv = engine.real_money_validation("ANTM", {}, {}, {}, {}, {})
        self.assertEqual(rv["foreign_flow_status"], "ACCUMULATING")
        self.assertEqual(rv["foreign_flow_score"], 12)
        self.assertEqual(rv["foreign_net_1d"], 48_850_000_000)
        self.assertEqual(rv["score"], 52)
        self.assertEqual(rv["foreign_flow_scoring_basis"], "ABSOLUTE_NET_IDR_1D")


if __name__ == "__main__":
    unittest.main()
