from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True, slots=True)
class PaperSignal:
    market: str
    symbol: str
    status: str
    signal_timestamp: str
    signal_close: float
    source: str


def extract_candidates(scan_payload: dict) -> tuple[PaperSignal, ...]:
    source = scan_payload.get("source", {}).get("name", "UNKNOWN")
    output: list[PaperSignal] = []
    for market in scan_payload.get("markets", []):
        for item in market.get("candidates", []):
            timestamp = item.get("signal_timestamp")
            close = item.get("signal_close")
            if timestamp and close is not None:
                output.append(
                    PaperSignal(
                        market=item["market"],
                        symbol=item["symbol"],
                        status=item["entry_status"],
                        signal_timestamp=timestamp,
                        signal_close=float(close),
                        source=source,
                    )
                )
    return tuple(output)


def append_journal(scan_path: str | Path, journal_path: str | Path) -> int:
    scan_payload = json.loads(Path(scan_path).read_text(encoding="utf-8"))
    signals = extract_candidates(scan_payload)
    destination = Path(journal_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    existing: list[dict] = []
    if destination.exists():
        existing = json.loads(destination.read_text(encoding="utf-8"))
    keys = {(row["market"], row["symbol"], row["signal_timestamp"]) for row in existing}
    added = 0
    for signal in signals:
        key = (signal.market, signal.symbol, signal.signal_timestamp)
        if key in keys:
            continue
        existing.append(
            {
                **asdict(signal),
                "recorded_at": datetime.now(timezone.utc).isoformat(),
                "outcome": "PENDING",
            }
        )
        keys.add(key)
        added += 1
    destination.write_text(json.dumps(existing, indent=2), encoding="utf-8")
    return added
