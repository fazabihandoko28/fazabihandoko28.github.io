"""Repository-level audit for HANZ Intelligence.

This audit performs no network calls. It verifies:
- Python source compilation
- unit tests
- the minimum CI workflow required for the current project stage
- repository hygiene

Every failed check prints its exact reason so GitHub Actions can be corrected
without guessing.
"""
from __future__ import annotations

import compileall
import json
import shutil
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
        "reasons": [] if process.returncode == 0 else ["Unit-test command returned a non-zero exit code."],
    }


def audit_workflow() -> dict[str, object]:
    # Minimum workflow contract for the current CI stage. Paper scan and
    # historical validation are optional jobs and must not make the CI audit fail.
    required_tokens = {
        "checkout": "actions/checkout@v4",
        "python_setup": "actions/setup-python@v5",
        "editable_install": "python -m pip install -e .",
        "source_compile": "python -m compileall -q src tools",
        "unit_tests": "python -m unittest discover -s tests -v",
        "repository_audit": "python tools/audit_repository.py",
    }

    if not WORKFLOW.exists():
        return {
            "passed": False,
            "workflow": str(WORKFLOW.relative_to(ROOT)),
            "missing": ["workflow file"],
            "reasons": [f"Missing workflow file: {WORKFLOW.relative_to(ROOT)}"],
        }

    text = WORKFLOW.read_text(encoding="utf-8")
    missing_keys = [name for name, token in required_tokens.items() if token not in text]
    reasons = [
        f"Workflow is missing required step/token '{name}': {required_tokens[name]}"
        for name in missing_keys
    ]
    return {
        "passed": not missing_keys,
        "workflow": str(WORKFLOW.relative_to(ROOT)),
        "missing": missing_keys,
        "reasons": reasons,
    }


def audit_hygiene() -> dict[str, object]:
    forbidden: list[str] = []
    reasons: list[str] = []

    for path in ROOT.rglob("*"):
        if ".git" in path.parts:
            continue
        relative = str(path.relative_to(ROOT))
        if path.is_dir() and path.name == "__pycache__":
            forbidden.append(relative)
            reasons.append(f"Generated Python cache directory is present: {relative}")
        elif path.is_file() and path.suffix == ".pyc":
            forbidden.append(relative)
            reasons.append(f"Generated Python bytecode file is present: {relative}")
        elif path.is_file() and path.name.startswith("HANZ_Session_"):
            forbidden.append(relative)
            reasons.append(f"Obsolete session document is present: {relative}")

    return {"passed": not forbidden, "forbidden": forbidden, "reasons": reasons}


def remove_generated_python_files() -> None:
    # Deepest paths first so nested cache directories are removed safely.
    cache_dirs = sorted(ROOT.rglob("__pycache__"), key=lambda p: len(p.parts), reverse=True)
    for cache in cache_dirs:
        shutil.rmtree(cache, ignore_errors=True)
    for pyc in ROOT.rglob("*.pyc"):
        try:
            pyc.unlink()
        except FileNotFoundError:
            pass


def print_result(name: str, result: dict[str, object]) -> None:
    status = "PASS" if result["passed"] else "FAIL"
    print(f"{name}: {status}")
    if not result["passed"]:
        for reason in result.get("reasons", []):
            print(f"  - {reason}")


def main() -> int:
    compile_ok = compileall.compile_dir(ROOT / "src", quiet=1, force=True)
    remove_generated_python_files()

    tests = run_tests()
    remove_generated_python_files()

    workflow = audit_workflow()
    hygiene = audit_hygiene()

    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "version": "0.6.2",
        "checks": {
            "source_compilation": {
                "passed": compile_ok,
                "reasons": [] if compile_ok else ["One or more Python files failed to compile."],
            },
            "unit_tests": tests,
            "github_workflow": workflow,
            "repository_hygiene": hygiene,
        },
    }
    report["passed"] = all(check["passed"] for check in report["checks"].values())

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")

    for name, result in report["checks"].items():
        print_result(name, result)
    print(f"audit_report: {REPORT.relative_to(ROOT)}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
