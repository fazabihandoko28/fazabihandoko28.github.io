from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from hanz_data import YahooFinanceProvider, load_yahoo_universe, require_paper_trade_source
from hanz_scanner import MarketScanReport, MarketScanner, ScanResult


def _serialize_result(item: ScanResult) -> dict:
    return {
        "market": item.market,
        "symbol": item.symbol,
        "tier": item.tier.value,
        "entry_status": item.decision.status.value,
        "selection_reasons": list(item.selection_reasons),
        "rejection_reasons": list(item.rejection_reasons),
        "vetoes": list(item.decision.vetoes),
        "signal_timestamp": item.snapshot.timestamp.isoformat() if item.snapshot else None,
        "signal_close": item.snapshot.close if item.snapshot else None,
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
    parser = argparse.ArgumentParser(description="HANZ free research paper scan")
    parser.add_argument("--universe", default="config/universe/pilot_universe.csv")
    parser.add_argument("--markets", nargs="+", default=["BEI", "ADX"])
    parser.add_argument("--period", default="1y")
    parser.add_argument("--interval", default="1d")
    parser.add_argument("--candidate-limit", type=int, default=5)
    parser.add_argument("--output", default="artifacts/paper_scans/latest.json")
    args = parser.parse_args()

    mappings = load_yahoo_universe(args.universe)
    provider = YahooFinanceProvider(mappings, period=args.period, interval=args.interval)
    policy = require_paper_trade_source(provider.source_name)
    scanner = MarketScanner(provider, candidate_limit=args.candidate_limit)
    reports = scanner.scan_markets(args.markets)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "PAPER_TRADE_RESEARCH",
        "source": {
            "name": policy.name,
            "grade": policy.grade.value,
            "delayed": policy.delayed,
            "allowed_for_live_trade": policy.allowed_for_live_trade,
            "notes": policy.notes,
        },
        "instruction": "Do not use this research feed for live-money execution.",
        "markets": [_serialize_report(report) for report in reports],
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Paper scan written to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
