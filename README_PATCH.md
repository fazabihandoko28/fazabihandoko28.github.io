# HANZ v1.0 Lean Storage Patch

This replaces timestamped repository history with bounded latest-only storage.

Repository keeps only:

- `dashboard/index.html`
- `dashboard/data/latest.json`
- `dashboard/last_update.txt`
- `artifacts/paper_scans/latest.json`
- `artifacts/paper_trading/journal.json`

Legacy `dashboard/history/` is removed automatically. GitHub Artifact remains a temporary 30-day backup only.

Upload/replace:

1. `.github/workflows/hanz-paper-scan.yml`
2. `tools/publish_scan_results.py`
3. `tests/test_publish_scan_results.py`
