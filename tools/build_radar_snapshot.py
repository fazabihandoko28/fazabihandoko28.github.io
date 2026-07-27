from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from hanz_radar import OpportunityRadar
from hanz_realtime.models import SymbolState


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--limit", type=int, default=25)
    args = parser.parse_args()

    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    states = []

    for item in payload:
        state = SymbolState(
            symbol=str(item["symbol"]).upper(),
            market=str(item.get("market", "BEI")).upper(),
            last_price=float(item["last_price"]),
            last_volume=float(item.get("last_volume", 0)),
            last_timestamp=datetime.fromisoformat(item["last_timestamp"]),
            tick_count=int(item.get("tick_count", 1)),
            cumulative_volume=float(item.get("cumulative_volume", 0)),
            price_change_pct=float(item.get("price_change_pct", 0)),
            spread_pct=(
                float(item["spread_pct"])
                if item.get("spread_pct") is not None else None
            ),
            velocity=float(item.get("velocity", 0)),
            anomaly_score=float(item.get("anomaly_score", 0)),
        )
        states.append(state)

    radar = OpportunityRadar(max_results=args.limit)
    result = radar.evaluate(states).to_dict()

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps({
        "ok": True,
        "signals": len(result["RADAR"]),
        "output": str(output),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
