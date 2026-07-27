import json
import tempfile
import unittest
from pathlib import Path

from hanz_app.foundation_integration import integrate_file, integrate_payload


class FoundationIntegrationTests(unittest.TestCase):
    def sample_payload(self):
        return {
            "generated_at": "2026-07-27T00:00:00+00:00",
            "mode": "PAPER_TRADE_RESEARCH",
            "source": {"name": "TEST", "grade": "RESEARCH"},
            "markets": [
                {
                    "market": "BEI",
                    "market_posture": "BULLISH",
                    "candidates": [
                        {
                            "symbol": "AAA",
                            "close": 100,
                            "resistance": 102,
                            "trend": "STRONG",
                            "momentum": "SUPPORTIVE",
                            "volume": "STRONG",
                            "liquidity": "STRONG",
                            "risk": "LOW",
                            "breakout": "SUPPORTIVE",
                            "relative_strength": "STRONG",
                            "market_signal": "SUPPORTIVE",
                        }
                    ],
                    "reviewed": [
                        {
                            "symbol": "BBB",
                            "trend": "SUPPORTIVE",
                            "momentum": "NEUTRAL",
                            "volume": "SUPPORTIVE",
                            "liquidity": "SUPPORTIVE",
                            "risk": "MEDIUM",
                            "resistance": "NEUTRAL",
                            "relative_strength": "SUPPORTIVE",
                            "market": "SUPPORTIVE",
                        }
                    ],
                }
            ],
        }

    def test_integration_outputs_indonesian_decision_fields(self):
        result = integrate_payload(self.sample_payload())
        decisions = result["markets"][0]["KEPUTUSAN"]
        self.assertEqual(len(decisions), 2)
        self.assertEqual(decisions[0]["SIMBOL"], "AAA")
        self.assertIn(decisions[0]["AKSI"], {"EKSEKUSI", "SIAGA", "AWAL"})
        self.assertIn("EVIDENCE", decisions[0])
        self.assertIn("RISIKO", decisions[0])
        self.assertLessEqual(len(decisions[0]["AKSI"].split()), 2)

    def test_duplicate_symbols_are_removed(self):
        payload = self.sample_payload()
        payload["markets"][0]["reviewed"].append(
            dict(payload["markets"][0]["candidates"][0])
        )
        result = integrate_payload(payload)
        symbols = [
            item["SIMBOL"]
            for item in result["markets"][0]["KEPUTUSAN"]
        ]
        self.assertEqual(symbols.count("AAA"), 1)

    def test_missing_evidence_never_ready(self):
        payload = {
            "markets": [{
                "market": "BEI",
                "candidates": [{"symbol": "MISS", "trend": "STRONG"}],
            }]
        }
        result = integrate_payload(payload)
        decision = result["markets"][0]["KEPUTUSAN"][0]
        self.assertEqual(decision["AKSI"], "DATA MINIM")

    def test_file_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "latest.json"
            output = Path(directory) / "decisions.json"
            source.write_text(
                json.dumps(self.sample_payload()),
                encoding="utf-8",
            )
            result = integrate_file(source, output)
            self.assertTrue(output.exists())
            saved = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(saved, result)


if __name__ == "__main__":
    unittest.main()
