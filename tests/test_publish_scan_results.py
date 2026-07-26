from __future__ import annotations

import json
import tempfile
import unittest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.publish_scan_results import publish


class PublishScanResultsTests(unittest.TestCase):
    def test_publishes_latest_only_and_removes_legacy_history(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            scan = root / "scan.json"
            report = root / "report.html"
            dashboard = root / "dashboard"
            history = dashboard / "history"
            history.mkdir(parents=True)
            (history / "old.json").write_text("{}", encoding="utf-8")

            scan.write_text(
                json.dumps({"generated_at": "2026-07-26T00:00:00+00:00"}),
                encoding="utf-8",
            )
            report.write_text("<html>HANZ</html>", encoding="utf-8")

            result = publish(scan=scan, report=report, dashboard_dir=dashboard)

            self.assertEqual(result["storage_mode"], "LEAN_LATEST_ONLY")
            self.assertTrue((dashboard / "index.html").is_file())
            self.assertTrue((dashboard / "data" / "latest.json").is_file())
            self.assertTrue((dashboard / "last_update.txt").is_file())
            self.assertFalse(history.exists())

    def test_missing_scan_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = root / "report.html"
            report.write_text("<html></html>", encoding="utf-8")
            with self.assertRaises(FileNotFoundError):
                publish(
                    scan=root / "missing.json",
                    report=report,
                    dashboard_dir=root / "dashboard",
                )


if __name__ == "__main__":
    unittest.main()
