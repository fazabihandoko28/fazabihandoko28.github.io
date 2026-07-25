import json
import tempfile
import unittest
from pathlib import Path

from hanz_paper import append_journal, extract_candidates


PAYLOAD = {
    "source": {"name": "YAHOO_FINANCE_RESEARCH_ONLY"},
    "markets": [
        {
            "candidates": [
                {
                    "market": "BEI",
                    "symbol": "BBRI",
                    "entry_status": "READY",
                    "signal_timestamp": "2026-07-24T00:00:00+00:00",
                    "signal_close": 3900,
                }
            ]
        }
    ],
}


class PaperJournalTests(unittest.TestCase):
    def test_extract_and_deduplicate(self):
        signals = extract_candidates(PAYLOAD)
        self.assertEqual(len(signals), 1)
        with tempfile.TemporaryDirectory() as tmp:
            scan = Path(tmp) / "scan.json"
            journal = Path(tmp) / "journal.json"
            scan.write_text(json.dumps(PAYLOAD), encoding="utf-8")
            self.assertEqual(append_journal(scan, journal), 1)
            self.assertEqual(append_journal(scan, journal), 0)
            rows = json.loads(journal.read_text(encoding="utf-8"))
            self.assertEqual(rows[0]["outcome"], "PENDING")


if __name__ == "__main__":
    unittest.main()
