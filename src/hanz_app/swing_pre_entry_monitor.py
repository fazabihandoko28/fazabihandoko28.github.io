import json
import urllib.parse

from firebase_admin import messaging

from .swing_trading_engine import (
    PUSH_DASHBOARD_URL,
    clean_ticker,
    firebase_app,
    idx_market_session,
    jakarta_date_string,
    jakarta_now,
    latest_intraday_quote,
    now_iso,
    supabase_request,
)


CANDIDATE_STATES = {
    "SETUP_READY",
    "PRE_ALERT",
    "EARLY_WATCH",
    "SWING_CONFIRMING",
    "SWING_WATCH",
}

ALERT_TYPE = "ENTERING_BUY_AREA"
MAX_CANDIDATES = 5


def fetch_pre_entry_candidates():
    rows = supabase_request(
        "GET",
        "hanz_swing_signal_monitor"
        "?select=ticker,state,score,price,entry_low,entry_high,stop_loss,target_1,target_2,updated_at"
        "&order=score.desc"
        "&limit=40",
    ) or []

    candidates = []
    for row in rows:
        state = str(row.get("state") or "").upper()
        score = row.get("score")
        try:
            score = float(score)
        except (TypeError, ValueError):
            score = 0.0

        if state not in CANDIDATE_STATES or score <= 0:
            continue

        try:
            low = float(row.get("entry_low"))
            high = float(row.get("entry_high"))
        except (TypeError, ValueError):
            continue

        if low <= 0 or high <= 0 or low > high:
            continue

        candidates.append(row)
        if len(candidates) >= MAX_CANDIDATES:
            break

    return candidates


def fetch_enabled_devices():
    return supabase_request(
        "GET",
        "hanz_push_devices"
        "?enabled=eq.true"
        "&select=user_id,installation_id,last_seen_at"
        "&order=last_seen_at.desc",
    ) or []


def event_key(user_id, ticker):
    return (
        f"PREENTRY:{user_id}:{clean_ticker(ticker)}:"
        f"{ALERT_TYPE}:{jakarta_date_string()}"
    )


def already_reserved(key):
    encoded = urllib.parse.quote(str(key), safe="")
    rows = supabase_request(
        "GET",
        f"hanz_push_log?event_key=eq.{encoded}&select=event_key&limit=1",
    ) or []
    return bool(rows)


def reserve_event(*, key, user_id, ticker):
    try:
        supabase_request(
            "POST",
            "hanz_push_log",
            {
                "event_key": key,
                "user_id": user_id,
                "portfolio_id": None,
                "ticker": clean_ticker(ticker),
                "alert_type": ALERT_TYPE,
                "status": "PENDING",
                "created_at": now_iso(),
            },
            prefer="return=minimal",
        )
        return True
    except Exception as exc:
        # Unique conflict means this alert was already sent/reserved.
        if "409" in str(exc):
            return False
        raise


def finish_event(key, status, error=None):
    encoded = urllib.parse.quote(str(key), safe="")
    payload = {
        "status": status,
        "updated_at": now_iso(),
    }
    if status == "SENT":
        payload["sent_at"] = now_iso()
    if error:
        payload["last_error"] = str(error)[:1000]

    try:
        supabase_request(
            "PATCH",
            f"hanz_push_log?event_key=eq.{encoded}",
            payload,
            prefer="return=minimal",
        )
    except Exception:
        pass


def release_event(key):
    encoded = urllib.parse.quote(str(key), safe="")
    try:
        supabase_request(
            "DELETE",
            f"hanz_push_log?event_key=eq.{encoded}",
            prefer="return=minimal",
        )
    except Exception:
        pass


def fmt_price(value):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return "—"
    if abs(value - round(value)) < 1e-9:
        return f"{int(round(value)):,}".replace(",", ".")
    return f"{value:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def send_entering_buy_area(*, row, live_price, user_id, installation_ids):
    ticker = clean_ticker(row.get("ticker"))
    low = float(row["entry_low"])
    high = float(row["entry_high"])
    key = event_key(user_id, ticker)

    if already_reserved(key):
        return "DUPLICATE"

    if not reserve_event(key=key, user_id=user_id, ticker=ticker):
        return "DUPLICATE"

    stop = fmt_price(row.get("stop_loss"))
    t1 = fmt_price(row.get("target_1"))
    t2 = fmt_price(row.get("target_2"))
    zone = f"{fmt_price(low)}–{fmt_price(high)}"
    current = fmt_price(live_price)

    title = f"HANZ {ticker} · ENTERING BUY AREA"
    body = (
        f"Price {current} masuk Best Buy Area {zone}. "
        f"Stop {stop} · T1 {t1} · T2 {t2}. "
        "Cek price action; jangan auto-buy."
    )

    try:
        app = firebase_app()
        if app is None:
            raise RuntimeError("Firebase is not configured")

        messages = [
            messaging.Message(
                data={
                    "title": title,
                    "body": body,
                    "message": body,
                    "ticker": ticker,
                    "alert_type": ALERT_TYPE,
                    "url": PUSH_DASHBOARD_URL,
                    "dedupe_key": key,
                },
                fid=fid,
            )
            for fid in installation_ids
            if fid
        ]

        if not messages:
            finish_event(key, "NO_DEVICE")
            return "NO_DEVICE"

        response = messaging.send_each(messages, app=app)
        finish_event(key, "SENT")
        print(
            f"PRE-ENTRY PUSH SENT {ticker} user={user_id} "
            f"success={response.success_count} failed={response.failure_count}",
            flush=True,
        )
        return "SENT"

    except Exception as exc:
        release_event(key)
        print(f"PRE-ENTRY PUSH FAILED {ticker}: {exc}", flush=True)
        return "ERROR"


def run_cycle():
    market = idx_market_session()
    now_wib = jakarta_now()

    print(
        "HANZ PRE-ENTRY MONITOR START | "
        f"IDX={market['state']} | WIB={now_wib.strftime('%Y-%m-%d %H:%M')}",
        flush=True,
    )

    if not market.get("is_trading_day") or market.get("state") not in {"SESSION_1", "SESSION_2"}:
        print("PRE-ENTRY MONITOR skipped: market is not actively trading.", flush=True)
        return

    candidates = fetch_pre_entry_candidates()
    devices = fetch_enabled_devices()

    devices_by_user = {}
    for row in devices:
        user_id = row.get("user_id")
        fid = str(row.get("installation_id") or "").strip()
        if user_id and fid:
            devices_by_user.setdefault(str(user_id), [])
            if fid not in devices_by_user[str(user_id)]:
                devices_by_user[str(user_id)].append(fid)

    summary = {
        "candidates": len(candidates),
        "users": len(devices_by_user),
        "inside_zone": 0,
        "sent": 0,
        "duplicate": 0,
        "errors": 0,
    }

    for row in candidates:
        ticker = row.get("ticker")
        try:
            quote = latest_intraday_quote(ticker)
            live_price = float(quote.get("price"))
            low = float(row.get("entry_low"))
            high = float(row.get("entry_high"))
        except Exception as exc:
            summary["errors"] += 1
            print(f"PRE-ENTRY QUOTE {clean_ticker(ticker)} failed: {exc}", flush=True)
            continue

        inside = low <= live_price <= high
        print(
            f"PRE-ENTRY {clean_ticker(ticker)} price={live_price} "
            f"zone={low}-{high} inside={inside}",
            flush=True,
        )

        if not inside:
            continue

        summary["inside_zone"] += 1

        for user_id, fids in devices_by_user.items():
            result = send_entering_buy_area(
                row=row,
                live_price=live_price,
                user_id=user_id,
                installation_ids=fids,
            )
            if result == "SENT":
                summary["sent"] += 1
            elif result == "DUPLICATE":
                summary["duplicate"] += 1
            elif result == "ERROR":
                summary["errors"] += 1

    print("HANZ PRE-ENTRY MONITOR complete: " + json.dumps(summary), flush=True)


def main():
    run_cycle()


if __name__ == "__main__":
    main()
