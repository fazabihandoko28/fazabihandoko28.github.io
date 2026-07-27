from datetime import datetime, timezone

from hanz_server.models import AlertEvent, EventPriority
from hanz_server.ntfy_notifier import NtfyNotifier


event = AlertEvent(
    event_id="manual-test",
    symbol="TINS",
    market="BEI",
    event_type="TEST",
    old_action="AWAL",
    new_action="SIAGA",
    priority=EventPriority.NORMAL,
    evidence=72,
    risk="SEDANG",
    trigger="close_above:3780",
    price=3440.0,
    created_at=datetime.now(timezone.utc).isoformat(),
    message_id="manual-test",
)

ok = NtfyNotifier().send(event)
print("NTFY TEST:", "BERHASIL" if ok else "GAGAL")
raise SystemExit(0 if ok else 1)
