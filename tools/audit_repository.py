"""Repository-level audit for HANZ Intelligence.

The audit intentionally avoids network calls. It verifies local structure,
Python syntax, unit tests, repository hygiene, and required CI workflow steps.
"""
from __future__ import annotations

import compileall
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "hanz-ci.yml"
REPORT = ROOT / "artifacts" / "audit" / "latest.json"


def run_tests() -> dict[str, object]:
    process = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    combined = (process.stdout + "\n" + process.stderr).strip()
    return {
        "passed": process.returncode == 0,
        "return_code": process.returncode,
        "output": combined,
    }


def audit_workflow() -> dict[str, object]:
    required = [
        "actions/checkout@v4",
        "actions/setup-python@v5",
        "python -m pip install -e .",
        "python -m unittest discover -s tests -v",
        "python -m hanz_app.paper_scan",
        "python -m hanz_app.validate_history",
    ]
    if not WORKFLOW.exists():
        return {"passed": False, "missing": ["workflow file"]}
    text = WORKFLOW.read_text(encoding="utf-8")
    missing = [item for item in required if item not in text]
    return {"passed": not missing, "missing": missing}


def audit_hygiene() -> dict[str, object]:
    forbidden = []
    for path in ROOT.rglob("*"):
        if ".git" in path.parts:
            continue
        if path.is_dir() and path.name == "__pycache__":
            forbidden.append(str(path.relative_to(ROOT)))
        elif path.is_file() and path.suffix == ".pyc":
            forbidden.append(str(path.relative_to(ROOT)))
        elif path.is_file() and path.name.startswith("HANZ_Session_"):
            forbidden.append(str(path.relative_to(ROOT)))
    return {"passed": not forbidden, "forbidden": forbidden}


def main() -> int:
    compile_ok = compileall.compile_dir(ROOT / "src", quiet=1, force=True)
    # Compilation creates pycache; clean it before hygiene inspection.
    for cache in (ROOT / "src").rglob("__pycache__"):
        for child in cache.iterdir():
            child.unlink()
        cache.rmdir()

    tests = run_tests()
    for cache in ROOT.rglob("__pycache__"):
        for child in cache.iterdir():
            if child.is_file():
                child.unlink()
        cache.rmdir()
    for pyc in ROOT.rglob("*.pyc"):
        pyc.unlink()
    workflow = audit_workflow()
    hygiene = audit_hygiene()
    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "version": "0.6.1",
        "checks": {
            "source_compilation": {"passed": compile_ok},
            "unit_tests": tests,
            "github_workflow": workflow,
            "repository_hygiene": hygiene,
        },
    }
    report["passed"] = all(check["passed"] for check in report["checks"].values())
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")

    for name, result in report["checks"].items():
        print(f"{name}: {'PASS' if result['passed'] else 'FAIL'}")
    print(f"audit_report: {REPORT.relative_to(ROOT)}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
