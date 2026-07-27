from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from hanz_realtime import RealtimeGateway, Tick


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay normalized HANZ ticks.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--top", type=int, default=10)
    args = parser.parse_args()

    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    gateway = RealtimeGateway()

    for item in payload:
        tick = Tick(
            symbol=str(item["symbol"]).upper(),
            market=str(item.get("market", "BEI")).upper(),
            price=float(item["price"]),
            volume=float(item["volume"]),
            timestamp=datetime.fromisoformat(item["timestamp"]),
            bid=float(item["bid"]) if item.get("bid") is not None else None,
            ask=float(item["ask"]) if item.get("ask") is not None else None,
            source=str(item.get("source", "REPLAY")),
        )
        gateway.ingest(tick)

    result = [
        {
            "SIMBOL": item.symbol,
            "PASAR": item.market,
            "SKOR": item.score,
            "ALASAN": item.reason,
            "WAKTU": item.updated_at.isoformat(),
        }
        for item in gateway.queue.ranked(args.top)
    ]
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
