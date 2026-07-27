import json
import unittest
from datetime import datetime, timezone

from hanz_server.models import AlertEvent, EventPriority
from hanz_server.ntfy_notifier import NtfyConfig, NtfyNotifier


class FakeResponse:
    status = 200
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False


class NtfyNotifierTests(unittest.TestCase):
    def event(self, action="EKSEKUSI", priority=EventPriority.HIGH):
        return AlertEvent(
            event_id="evt-1",
            symbol="TINS",
            market="BEI",
            event_type="UPGRADE",
            old_action="SIAGA",
            new_action=action,
            priority=priority,
            evidence=82,
            risk="SEDANG",
            trigger="close_above:3780",
            price=3790.0,
            created_at=datetime.now(timezone.utc).isoformat(),
            message_id="msg-1",
        )

    def test_payload(self):
        notifier = NtfyNotifier(NtfyConfig(
            "https://ntfy.sh",
            "secret-topic",
            dashboard_url="https://example.test/",
        ))
        payload = notifier.build_payload(self.event())
        self.assertEqual(payload["topic"], "secret-topic")
        self.assertEqual(payload["priority"], 4)
        self.assertIn("EKSEKUSI", payload["title"])
        self.assertIn("EVIDENCE: 82", payload["message"])
        self.assertEqual(payload["click"], "https://example.test/")

    def test_critical_priority(self):
        notifier = NtfyNotifier(NtfyConfig(
            "https://ntfy.sh",
            "secret-topic",
        ))
        payload = notifier.build_payload(
            self.event("JUAL", EventPriority.CRITICAL)
        )
        self.assertEqual(payload["priority"], 5)
        self.assertIn("red_circle", payload["tags"])

    def test_bearer_token(self):
        captured = {}
        def opener(request, timeout):
            captured["auth"] = request.headers.get("Authorization")
            captured["body"] = json.loads(
                request.data.decode("utf-8")
            )
            return FakeResponse()

        notifier = NtfyNotifier(
            NtfyConfig(
                "https://ntfy.sh",
                "secret-topic",
                token="tk_secret",
            ),
            opener=opener,
        )
        self.assertTrue(notifier.send(self.event()))
        self.assertEqual(captured["auth"], "Bearer tk_secret")
        self.assertEqual(captured["body"]["topic"], "secret-topic")

    def test_network_failure(self):
        def opener(request, timeout):
            raise OSError("offline")

        notifier = NtfyNotifier(
            NtfyConfig("https://ntfy.sh", "secret-topic"),
            opener=opener,
        )
        self.assertFalse(notifier.send(self.event()))


if __name__ == "__main__":
    unittest.main()
