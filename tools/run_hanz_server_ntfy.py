from __future__ import annotations

import argparse

from hanz_server import HanzRealtimeService, SQLiteStateStore
from hanz_server.event_engine import EventEngine, EventPolicy
from hanz_server.http_api import run_http_server
from hanz_server.ntfy_notifier import NtfyNotifier


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--db", default="data/hanz_realtime.db")
    parser.add_argument("--cooldown", type=int, default=300)
    parser.add_argument("--min-evidence", type=int, default=55)
    args = parser.parse_args()

    service = HanzRealtimeService(
        store=SQLiteStateStore(args.db),
        engine=EventEngine(EventPolicy(
            cooldown_seconds=args.cooldown,
            min_evidence=args.min_evidence,
        )),
        notifiers=[NtfyNotifier()],
    )
    run_http_server(service, args.host, args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
