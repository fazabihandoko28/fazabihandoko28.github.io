import json
import os
import sys
from datetime import datetime, timezone

import firebase_admin
import requests
from firebase_admin import credentials, messaging


def main():
    service_account_raw = os.getenv(
        "FIREBASE_SERVICE_ACCOUNT_JSON", ""
    ).strip()
    supabase_url = os.getenv(
        "SUPABASE_URL", ""
    ).rstrip("/")
    supabase_key = os.getenv(
        "SUPABASE_SECRET_KEY", ""
    ).strip()

    if not service_account_raw:
        print("ERROR: FIREBASE_SERVICE_ACCOUNT_JSON is missing.")
        return 1

    if not supabase_url or not supabase_key:
        print("ERROR: Supabase secrets are missing.")
        return 1

    headers = {
        "apikey": supabase_key,
        "Authorization": f"Bearer {supabase_key}",
        "Content-Type": "application/json",
    }

    def get_enabled_devices():
        url = (
            f"{supabase_url}/rest/v1/hanz_push_devices"
            "?enabled=eq.true"
            "&select=id,installation_id,last_seen_at,platform"
            "&order=last_seen_at.desc"
            "&limit=10"
        )
        response = requests.get(
            url,
            headers=headers,
            timeout=20,
        )
        response.raise_for_status()
        return response.json()

    def disable_fid(fid):
        url = (
            f"{supabase_url}/rest/v1/hanz_push_devices"
            f"?installation_id=eq.{fid}"
        )
        response = requests.patch(
            url,
            headers=headers,
            json={
                "enabled": False,
                "last_seen_at": datetime.now(
                    timezone.utc
                ).isoformat(),
            },
            timeout=20,
        )
        response.raise_for_status()

    service_account = json.loads(service_account_raw)

    if not firebase_admin._apps:
        firebase_admin.initialize_app(
            credentials.Certificate(service_account)
        )

    devices = get_enabled_devices()

    if not devices:
        print("ERROR: No enabled HANZ FID found.")
        return 1

    for row in devices:
        fid = (
            row.get("installation_id") or ""
        ).strip()

        if not fid:
            continue

        print(
            "Trying FID:",
            "last_seen=",
            row.get("last_seen_at"),
            "platform=",
            row.get("platform"),
        )

        message = messaging.Message(
            fid=fid,
            data={
                "title": "HANZ SELF-HEAL TEST",
                "body": "Self-healing FID delivery is working.",
                "message": "Self-healing FID delivery is working.",
                "ticker": "TEST",
                "alert_type": "TEST_PUSH",
                "dedupe_key": "hanz-self-heal-test",
                "url": "/dashboard/swing/",
            },
        )

        try:
            message_id = messaging.send(message)
            print("HANZ SELF-HEAL TEST SENT SUCCESSFULLY")
            print("Firebase message id:", message_id)
            return 0

        except messaging.UnregisteredError:
            print(
                "FID is NotRegistered. "
                "Disabling it in Supabase and trying next."
            )
            disable_fid(fid)
            continue

        except Exception as exc:
            print(
                "Unexpected push failure:",
                type(exc).__name__,
                exc,
            )
            return 1

    print(
        "ERROR: All currently enabled FIDs were "
        "stale/unregistered."
    )
    print(
        "Open HANZ with Push ON to create a fresh "
        "registration, then run this workflow again."
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
