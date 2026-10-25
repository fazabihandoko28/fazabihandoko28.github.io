"""Read-only G1 FAST intraday evidence check; never updates G0 or signals BUY."""
import argparse
import json
import os
from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

WIB = ZoneInfo("Asia/Jakarta")
FRESHNESS_SECONDS = 1800
G1_MIN_SYMBOLS = 198


def timestamp(value):
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is not None:
            return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        pass
    return None


def session_open(now):
    local = now.astimezone(WIB)
    if local.weekday() >= 5 or local.date().isoformat() in {
        x.strip() for x in os.getenv("HANZ_IDX_HOLIDAYS", "").split(",") if x.strip()
    }:
        return False
    minute = local.hour * 60 + local.minute
    friday = local.weekday() == 4
    return (540 <= minute < (690 if friday else 720)
            or (840 if friday else 810) <= minute < 950)


def evaluate(row, now):
    """Conservatively verify G1 LIVE evidence, not G0 operational PASS."""
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    now = now.astimezone(timezone.utc)
    open_now = session_open(now)
    reasons = []
    if not isinstance(row, dict):
        row = {}
    status = str(row.get("data_status") or "UNKNOWN").upper()
    if status != "FRESH":
        reasons.append("source_status_not_fresh")
    try:
        coverage = int(row.get("symbols_monitored"))
    except (ValueError, TypeError, OverflowError):
        coverage = 0
    if coverage < G1_MIN_SYMBOLS:
        reasons.append("g1_coverage_incomplete")
    scan = timestamp(row.get("last_scan_at"))
    bar = timestamp(row.get("last_market_bar_at"))
    for label, dt in (("scan", scan), ("bar", bar)):
        if dt is None:
            reasons.append(f"{label}_timestamp_invalid")
        elif not 0 <= (now - dt).total_seconds() <= FRESHNESS_SECONDS:
            reasons.append(f"{label}_not_fresh")
    # A completed scan cannot contain a market bar timestamped after the scan.
    # Both timestamps can individually be fresh while their order is impossible.
    if scan is not None and bar is not None and bar > scan:
        reasons.append("bar_after_scan")
    if bar is not None and bar.astimezone(WIB).date() != now.astimezone(WIB).date():
        reasons.append("bar_not_current_idx_session")
    if not open_now:
        reasons.append("idx_session_closed")
    live = not reasons
    return {
        "g1_fast_live": "LIVE" if live else "STALE",
        "idx_session_open": open_now,
        "g1_fast_live_verified": live,
        "source_status": status,
        "symbols_monitored": coverage,
        "last_scan_at": row.get("last_scan_at"),
        "last_market_bar_at": row.get("last_market_bar_at"),
        "blockers": reasons,
        "g1_closed": False,  # Other G1 gates must be verified separately.
    }


def read_health():
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_SECRET_KEY", "")
    if not url or not key:
        raise RuntimeError("G1 FAST read-only evidence credentials unavailable")
    path = "/rest/v1/hanz_fast_health?" + urlencode({
        "id": "eq.bei-fast",
        "select": "data_status,symbols_monitored,last_scan_at,last_market_bar_at",
        "limit": "1",
    })
    request = Request(url + path, headers={
        "apikey": key, "Authorization": "Bearer " + key, "Accept": "application/json",
    }, method="GET")
    with urlopen(request, timeout=15) as response:
        rows = json.load(response)
    return rows[0] if isinstance(rows, list) and rows else {}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fail-during-live-session", action="store_true")
    args = parser.parse_args()
    now = datetime.now(timezone.utc)
    try:
        row = read_health()
        report = evaluate(row, now)
    except Exception as exc:
        report = evaluate({}, now)
        report["blockers"].append("read_only_health_query_unavailable:" + type(exc).__name__)
    print("G1 FAST READ-ONLY EVIDENCE: " + json.dumps(report, sort_keys=True), flush=True)
    summary = os.getenv("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as file:
            file.write("\n### G1 FAST intraday evidence (read-only)\n\n")
            file.write(f"Status: **{report['g1_fast_live']}**; source: **{report['source_status']}**; ")
            file.write(f"coverage: **{report['symbols_monitored']}/{G1_MIN_SYMBOLS}**; ")
            file.write(f"IDX open: **{report['idx_session_open']}**.\n\n")
            file.write("Blockers: " + ", ".join(report["blockers"]) + "\n")
            file.write("\nThis check does not certify G1 CLOSED or generate trading signals.\n")
    if args.fail_during_live_session and report["idx_session_open"] and not report["g1_fast_live_verified"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
