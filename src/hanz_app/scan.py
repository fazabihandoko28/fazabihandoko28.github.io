from __future__ import annotations

import argparse
import json
from pathlib import Path

from hanz_data import DirectoryCsvProvider
from hanz_scanner import MarketScanner


def main() -> int:
    parser = argparse.ArgumentParser(description="HANZ Intelligence autonomous market scan")
    parser.add_argument("--data-root", required=True, help="Directory containing BEI/ and ADX/ CSV folders")
    parser.add_argument("--markets", nargs="+", default=["BEI", "ADX"])
    parser.add_argument("--output", help="Optional JSON output path")
    args = parser.parse_args()

    scanner = MarketScanner(DirectoryCsvProvider(args.data_root))
    results = scanner.scan_markets(args.markets)
    payload = [
        {
            "market": item.market,
            "symbol": item.symbol,
            "status": item.decision.status.value,
            "reasons": item.decision.reasons,
            "vetoes": item.decision.vetoes,
            "timestamp": item.snapshot.timestamp.isoformat() if item.snapshot else None,
            "close": item.snapshot.close if item.snapshot else None,
            "audit": item.decision.audit,
            "error": item.error,
        }
        for item in results
    ]
    rendered = json.dumps(payload, indent=2)
    if args.output:
        Path(args.output).write_text(rendered, encoding="utf-8")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
