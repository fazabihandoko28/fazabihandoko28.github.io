"""Shared test bootstrap for direct local execution.

This keeps the src-layout explicit without requiring an editable install merely
for running the unit test suite from a checked-out repository.
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"

src_path = str(SRC_ROOT)
if src_path not in sys.path:
    sys.path.insert(0, src_path)
