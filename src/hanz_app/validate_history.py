from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from hanz_data import YahooFinanceProvider, load_yahoo_universe, require_paper_trade_source
from hanz_validation import WalkForwardValidator


def main() -> int:
    parser = argparse.ArgumentParser(description="HANZ no-lookahead historical validation")
    parser.add_argument("--universe", default="config/universe/pilot_universe.csv")
    parser.add_argument("--markets", nargs="+", default=["BEI"])
    parser.add_argument("--period", default="5y")
    parser.add_argument("--interval", default="1d")
    parser.add_argument("--minimum-bars", type=int, default=60)
    parser.add_argument("--horizon-bars", type=int, default=5)
    parser.add_argument("--step-bars", type=int, default=5)
    parser.add_argument("--target-pct", type=float, default=0.04)
    parser.add_argument("--stop-pct", type=float, default=0.025)
    parser.add_argument("--output", default="artifacts/historical_validation/latest.json")
    args = parser.parse_args()

    mappings = load_yahoo_universe(args.universe)
    provider = YahooFinanceProvider(mappings, period=args.period, interval=args.interval)
    policy = require_paper_trade_source(provider.source_name)
    validator = WalkForwardValidator(
        minimum_bars=args.minimum_bars,
        horizon_bars=args.horizon_bars,
        step_bars=args.step_bars,
        target_pct=args.target_pct,
        stop_pct=args.stop_pct,
    )
    reports = []
    errors = []
    for market in args.markets:
        for symbol in provider.list_symbols(market):
            try:
                series = provider.load_series(market, symbol)
                reports.append(validator.validate(series).to_dict(include_events=True))
            except Exception as exc:
                errors.append({"market": market, "symbol": symbol, "error": str(exc)})

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "NO_LOOKAHEAD_HISTORICAL_VALIDATION",
        "source": {
            "name": policy.name,
            "grade": policy.grade.value,
            "allowed_for_live_trade": policy.allowed_for_live_trade,
        },
        "configuration": {
            "minimum_bars": args.minimum_bars,
            "horizon_bars": args.horizon_bars,
            "step_bars": args.step_bars,
            "target_pct": args.target_pct,
            "stop_pct": args.stop_pct,
        },
        "reports": reports,
        "errors": errors,
        "instruction": "Observed historical validation only; not a profit forecast.",
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Historical validation written to {output}; reports={len(reports)} errors={len(errors)}")
    return 0 if reports else 2


if __name__ == "__main__":
    raise SystemExit(main())
