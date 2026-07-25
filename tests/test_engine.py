from bootstrap import PROJECT_ROOT  # noqa: F401

import unittest


from hanz_core import EntryStatus, Evidence, Signal, decide_entry


def e(name, signal, critical=False):
    return Evidence(name, signal, "test", "2026-07-25T10:00:00Z", critical)


class TestHanzCore(unittest.TestCase):
    def base_ready(self):
        return [
            e("data_freshness", Signal.POSITIVE, True),
            e("liquidity", Signal.POSITIVE, True),
            e("spread", Signal.POSITIVE),
            e("market_regime", Signal.POSITIVE),
            e("price_structure", Signal.POSITIVE),
            e("volume_confirmation", Signal.POSITIVE),
            e("resistance", Signal.NEUTRAL),
            e("risk_reward", Signal.POSITIVE, True),
            e("historical_behaviour", Signal.POSITIVE),
        ]

    def test_ready(self):
        self.assertEqual(decide_entry(self.base_ready()).status, EntryStatus.READY)

    def test_hard_veto_rejects(self):
        data = self.base_ready()
        data = [x for x in data if x.name != "liquidity"] + [e("liquidity", Signal.NEGATIVE, True)]
        d = decide_entry(data)
        self.assertEqual(d.status, EntryStatus.REJECT)
        self.assertIn("liquidity", d.vetoes)

    def test_missing_required_waits(self):
        data = [x for x in self.base_ready() if x.name != "resistance"]
        self.assertEqual(decide_entry(data).status, EntryStatus.WAIT)

    def test_contradiction_waits(self):
        data = self.base_ready() + [
            e("news", Signal.WARNING),
            e("money_flow", Signal.NEGATIVE),
        ]
        self.assertEqual(decide_entry(data).status, EntryStatus.WAIT)

    def test_repeatability(self):
        data = self.base_ready()
        self.assertEqual(decide_entry(data), decide_entry(data))


if __name__ == "__main__":
    unittest.main()
