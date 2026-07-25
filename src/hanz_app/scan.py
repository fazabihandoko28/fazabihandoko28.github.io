from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from hanz_data import DirectoryCsvProvider
from hanz_scanner import MarketScanReport, MarketScanner, ScanResult


def _serialize_result(item: ScanResult) -> dict:
    return {
        "market": item.market,
        "symbol": item.symbol,
        "tier": item.tier.value,
        "status": item.decision.status.value,
        "selection_reasons": list(item.selection_reasons),
        "rejection_reasons": list(item.rejection_reasons),
        "vetoes": item.decision.vetoes,
        "timestamp": item.snapshot.timestamp.isoformat() if item.snapshot else None,
        "close": item.snapshot.close if item.snapshot else None,
        "evidence": {
            "positive": list(item.evidence.positive),
            "neutral": list(item.evidence.neutral),
            "warning": list(item.evidence.warning),
            "negative": list(item.evidence.negative),
            "unknown": list(item.evidence.unknown),
        },
        "audit": item.decision.audit,
        "error": item.error,
    }


def _serialize_report(report: MarketScanReport) -> dict:
    return {
        "market": report.market,
        "universe_size": report.universe_size,
        "candidate_count": len(report.candidates),
        "reviewed_count": len(report.reviewed),
        "rejected_count": len(report.rejected),
        "error_count": len(report.errors),
        "candidates": [_serialize_result(item) for item in report.candidates],
        "reviewed": [_serialize_result(item) for item in report.reviewed],
        "rejected": [_serialize_result(item) for item in report.rejected],
        "errors": [_serialize_result(item) for item in report.errors],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="HANZ Intelligence autonomous market scan")
    parser.add_argument("--data-root", required=True, help="Directory containing BEI/ and ADX/ CSV folders")
    parser.add_argument("--markets", nargs="+", default=["BEI", "ADX"])
    parser.add_argument("--candidate-limit", type=int, default=5)
    parser.add_argument("--output", help="Optional JSON output path")
    args = parser.parse_args()

    scanner = MarketScanner(
        DirectoryCsvProvider(args.data_root),
        candidate_limit=args.candidate_limit,
    )
    reports = scanner.scan_markets(args.markets)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "PAPER_SCAN",
        "disclaimer": "Evidence screening only; not an order or profit guarantee.",
        "markets": [_serialize_report(report) for report in reports],
    }
    rendered = json.dumps(payload, indent=2)
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
