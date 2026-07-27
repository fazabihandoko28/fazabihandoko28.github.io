from __future__ import annotations

import argparse
import json
import signal
from datetime import datetime, timezone
from pathlib import Path
from threading import Event, Thread

from hanz_providers import (
    TwelveDataConfig,
    TwelveDataMessageParser,
    TwelveDataProvider,
)
from hanz_providers.symbol_map import load_symbol_map
from hanz_radar import OpportunityRadar
from hanz_radar.bridge import RadarDecisionBridge
from hanz_realtime import RealtimeGateway
from hanz_server import HanzRealtimeService, SQLiteStateStore


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run Twelve Data -> Gateway -> Radar -> Event Engine."
    )
    parser.add_argument("--symbols", default="")
    parser.add_argument("--symbol-map")
    parser.add_argument("--market", default="BEI")
    parser.add_argument("--db", default="data/hanz_realtime.db")
    parser.add_argument("--snapshot", default="data/radar_live.json")
    parser.add_argument("--rank-seconds", type=int, default=15)
    args = parser.parse_args()

    symbols = [
        item.strip()
        for item in args.symbols.split(",")
        if item.strip()
    ] or None
    config = TwelveDataConfig.from_env(
        symbols=symbols,
        market=args.market,
    )

    aliases = (
        load_symbol_map(args.symbol_map)
        if args.symbol_map else {}
    )
    parser_ = TwelveDataMessageParser(
        market=config.market,
        source=config.source,
        symbol_aliases=aliases,
    )

    gateway = RealtimeGateway()
    radar = OpportunityRadar(max_results=25)
    bridge = RadarDecisionBridge(radar)
    service = HanzRealtimeService(
        store=SQLiteStateStore(args.db),
    )
    stop = Event()

    def on_tick(tick):
        gateway.ingest(tick)

    def on_status(payload):
        print(json.dumps(payload, ensure_ascii=False))

    provider = TwelveDataProvider(
        config,
        on_tick=on_tick,
        on_status=on_status,
        parser=parser_,
    )

    def rank_loop():
        snapshot_path = Path(args.snapshot)
        while not stop.wait(args.rank_seconds):
            now = datetime.now(timezone.utc)
            snapshot = radar.evaluate(gateway.states.values(), now=now)
            snapshot_path.parent.mkdir(parents=True, exist_ok=True)
            snapshot_path.write_text(
                json.dumps(
                    snapshot.to_dict(),
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            for decision in bridge.decisions(
                gateway.states.values(),
                now=now,
            ):
                service.process_decision(decision)

    def shutdown(*_):
        stop.set()
        provider.stop()

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    worker = Thread(target=rank_loop, daemon=True)
    worker.start()
    provider.run_forever()
    worker.join(timeout=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
