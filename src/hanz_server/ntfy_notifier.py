from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable

from .models import AlertEvent, EventPriority


@dataclass(frozen=True)
class NtfyConfig:
    server_url: str
    topic: str
    token: str | None = None
    dashboard_url: str | None = None
    timeout_seconds: int = 15

    @classmethod
    def from_env(cls) -> "NtfyConfig":
        topic = os.getenv("HANZ_NTFY_TOPIC", "").strip()
        if not topic:
            raise ValueError("HANZ_NTFY_TOPIC is required")
        return cls(
            server_url=os.getenv("HANZ_NTFY_SERVER", "https://ntfy.sh").rstrip("/"),
            topic=topic,
            token=os.getenv("HANZ_NTFY_TOKEN") or None,
            dashboard_url=os.getenv(
                "HANZ_DASHBOARD_URL",
                "https://fazabihandoko28.github.io/",
            ),
        )


class NtfyNotifier:
    def __init__(
        self,
        config: NtfyConfig | None = None,
        opener: Callable[..., object] | None = None,
    ) -> None:
        self.config = config or NtfyConfig.from_env()
        self._opener = opener or urllib.request.urlopen

    def send(self, event: AlertEvent) -> bool:
        request = urllib.request.Request(
            f"{self.config.server_url}/",
            data=json.dumps(
                self.build_payload(event),
                ensure_ascii=False,
            ).encode("utf-8"),
            method="POST",
            headers={
                "Content-Type": "application/json; charset=utf-8",
                **self._auth_headers(),
            },
        )
        try:
            with self._opener(
                request,
                timeout=self.config.timeout_seconds,
            ) as response:
                return 200 <= int(getattr(response, "status", 200)) < 300
        except (urllib.error.URLError, TimeoutError, OSError, ValueError):
            return False

    def build_payload(self, event: AlertEvent) -> dict[str, object]:
        payload: dict[str, object] = {
            "topic": self.config.topic,
            "title": f"HANZ • {event.symbol} • {event.new_action}",
            "message": self._message(event),
            "priority": {
                EventPriority.LOW: 2,
                EventPriority.NORMAL: 3,
                EventPriority.HIGH: 4,
                EventPriority.CRITICAL: 5,
            }[event.priority],
            "tags": self._tags(event),
        }
        if self.config.dashboard_url:
            payload["click"] = self.config.dashboard_url
            payload["actions"] = [{
                "action": "view",
                "label": "Buka HANZ",
                "url": self.config.dashboard_url,
                "clear": True,
            }]
        return payload

    def _auth_headers(self) -> dict[str, str]:
        if not self.config.token:
            return {}
        return {"Authorization": f"Bearer {self.config.token}"}

    @staticmethod
    def _tags(event: AlertEvent) -> list[str]:
        mapping = {
            "AWAL": ["mag", "chart_with_upwards_trend"],
            "SIAGA": ["eyes", "chart_with_upwards_trend"],
            "EKSEKUSI": ["zap", "green_circle"],
            "TAHAN": ["shield", "blue_circle"],
            "LEPAS": ["warning", "orange_circle"],
            "JUAL": ["rotating_light", "red_circle"],
        }
        return ["hanz", *mapping.get(
            event.new_action,
            ["information_source"],
        )]

    @staticmethod
    def _message(event: AlertEvent) -> str:
        lines = [
            f"AKSI: {event.new_action}",
            f"EVIDENCE: {event.evidence}",
            f"RISIKO: {event.risk}",
        ]
        if event.price is not None:
            lines.append(f"HARGA: {event.price:g}")
        if event.trigger:
            lines.append(f"PEMICU: {event.trigger}")
        return "\n".join(lines)
