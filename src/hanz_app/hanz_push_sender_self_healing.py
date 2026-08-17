"""
HANZ Firebase push sender with automatic stale-FID cleanup.

Expected environment:
- FIREBASE_SERVICE_ACCOUNT_JSON
- SUPABASE_URL
- SUPABASE_SECRET_KEY
"""

import json
import os
from datetime import datetime, timezone

import firebase_admin
import requests
from firebase_admin import credentials, messaging
from firebase_admin.exceptions import FirebaseError


SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_SECRET_KEY = os.getenv("SUPABASE_SECRET_KEY", "")
FIREBASE_SERVICE_ACCOUNT_JSON = os.getenv(
    "FIREBASE_SERVICE_ACCOUNT_JSON", ""
)


def _headers():
    return {
        "apikey": SUPABASE_SECRET_KEY,
        "Authorization": f"Bearer {SUPABASE_SECRET_KEY}",
        "Content-Type": "application/json",
    }


def _ensure_firebase():
    if firebase_admin._apps:
        return

    if not FIREBASE_SERVICE_ACCOUNT_JSON:
        raise RuntimeError(
            "FIREBASE_SERVICE_ACCOUNT_JSON is missing"
        )

    service_account = json.loads(
        FIREBASE_SERVICE_ACCOUNT_JSON
    )

    firebase_admin.initialize_app(
        credentials.Certificate(service_account)
    )


def disable_fid(fid: str) -> None:
    if not fid or not SUPABASE_URL or not SUPABASE_SECRET_KEY:
        return

    endpoint = (
        f"{SUPABASE_URL}/rest/v1/hanz_push_devices"
        f"?installation_id=eq.{fid}"
    )

    requests.patch(
        endpoint,
        headers=_headers(),
        json={
            "enabled": False,
            "last_seen_at": datetime.now(
                timezone.utc
            ).isoformat(),
        },
        timeout=20,
    ).raise_for_status()


def send_to_fid(
    fid: str,
    *,
    title: str,
    body: str,
    ticker: str = "",
    alert_type: str = "",
    url: str = "/dashboard/swing/",
    dedupe_key: str = "",
):
    _ensure_firebase()

    message = messaging.Message(
        fid=fid,
        data={
            "title": title,
            "body": body,
            "message": body,
            "ticker": ticker,
            "alert_type": alert_type,
            "url": url,
            "dedupe_key": dedupe_key,
        },
    )

    try:
        return messaging.send(message)

    except messaging.UnregisteredError:
        # Firebase has explicitly told us this registration is dead.
        # Remove it from future sends immediately.
        disable_fid(fid)
        return None

    except FirebaseError:
        raise
