from __future__ import annotations

import argparse
from hanz_paper import append_journal


def main() -> int:
    parser = argparse.ArgumentParser(description="Append HANZ paper candidates to journal")
    parser.add_argument("--scan", default="artifacts/paper_scans/latest.json")
    parser.add_argument("--journal", default="artifacts/paper_trading/journal.json")
    args = parser.parse_args()
    added = append_journal(args.scan, args.journal)
    print(f"Added {added} new paper signal(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
