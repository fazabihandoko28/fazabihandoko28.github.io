from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path


def publish(*, scan: Path, report: Path, dashboard_dir: Path) -> dict[str, str]:
    """Publish only the latest HANZ outputs, keeping repository growth bounded."""
    if not scan.is_file():
        raise FileNotFoundError(f"Scan file not found: {scan}")
    if not report.is_file():
        raise FileNotFoundError(f"Dashboard report not found: {report}")

    payload = json.loads(scan.read_text(encoding="utf-8"))

    dashboard_dir.mkdir(parents=True, exist_ok=True)
    data_dir = dashboard_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    latest_json = data_dir / "latest.json"
    latest_html = dashboard_dir / "index.html"

    shutil.copy2(scan, latest_json)
    if report.resolve() != latest_html.resolve():
        shutil.copy2(report, latest_html)

    generated_at = payload.get("generated_at") or payload.get("generated_at_utc")
    if generated_at:
        try:
            stamp_dt = datetime.fromisoformat(str(generated_at).replace("Z", "+00:00"))
        except ValueError:
            stamp_dt = datetime.now(timezone.utc)
    else:
        stamp_dt = datetime.now(timezone.utc)
    stamp_dt = stamp_dt.astimezone(timezone.utc)

    last_update = dashboard_dir / "last_update.txt"
    last_update.write_text(stamp_dt.isoformat() + "\n", encoding="utf-8")

    # Remove legacy timestamped history from the earlier publishing design.
    history_dir = dashboard_dir / "history"
    if history_dir.exists():
        shutil.rmtree(history_dir)

    return {
        "latest_html": str(latest_html),
        "latest_json": str(latest_json),
        "last_update": str(last_update),
        "storage_mode": "LEAN_LATEST_ONLY",
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Publish the latest HANZ scan without accumulating timestamped history."
    )
    parser.add_argument("--scan", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--dashboard-dir", default=Path("dashboard"), type=Path)
    args = parser.parse_args()

    result = publish(
        scan=args.scan,
        report=args.report,
        dashboard_dir=args.dashboard_dir,
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
