import unittest

from hanz_app.foundation_integration import integrate_payload


class AdapterV2Tests(unittest.TestCase):
    def test_real_tins_structure_is_mapped(self):
        payload = {
            "markets": [{
                "market": "BEI",
                "reviewed": [{
                    "symbol": "TINS",
                    "tier": "OBSERVE",
                    "entry_status": "HIGH_RISK",
                    "signal_close": 3440.0,
                    "technical": {
                        "ema20": 3493.2368,
                        "ema50": 3473.0707,
                        "rsi14": 49.45,
                        "atr14": 146.42,
                        "relative_volume20": 0.57,
                        "resistance20": 3780.0,
                        "support20": 3220.0
                    },
                    "evidence": {
                        "positive": ["data_freshness", "liquidity"],
                        "neutral": ["extension_risk", "market_regime", "resistance"],
                        "warning": [
                            "price_structure",
                            "risk_reward",
                            "volume_confirmation"
                        ],
                        "negative": [],
                        "unknown": []
                    }
                }]
            }]
        }

        result = integrate_payload(payload)
        decision = result["markets"][0]["KEPUTUSAN"][0]

        self.assertEqual(decision["SIMBOL"], "TINS")
        self.assertGreater(decision["EVIDENCE"], 0)
        self.assertGreater(decision["CAKUPAN"], 0)
        self.assertNotEqual(decision["RISIKO"], "BELUM ADA")
        self.assertNotEqual(decision["AKSI"], "DATA MINIM")


if __name__ == "__main__":
    unittest.main()
