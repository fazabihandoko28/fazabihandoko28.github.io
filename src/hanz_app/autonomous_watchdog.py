"""HANZ server-side watchdog. Runs independently via GitHub Actions cron."""
import datetime as dt
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

WIB = ZoneInfo("Asia/Jakarta")
UTC = dt.timezone.utc

def request(url, headers):
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=20) as response:
        return json.load(response)

def main():
    now = dt.datetime.now(UTC)
    local = now.astimezone(WIB)
    base = os.environ["SUPABASE_URL"].rstrip("/")
    key = os.environ["SUPABASE_SECRET_KEY"]
    headers = {"apikey": key, "Authorization": "Bearer " + key}
    issues = []
    result = {"checked_at": now.isoformat(), "wib": local.isoformat(), "issues": issues}
    try:
        rows = request(base + "/rest/v1/hanz_premarket_bullish_current?select=rank,ticker,prediction_label,source_bar_at,generated_at&order=rank.asc&limit=10", headers)
        result["radar_count"] = len(rows)
        result["tickers"] = [r.get("ticker") for r in rows]
        if not rows:
            issues.append("PMR80_EMPTY")
        elif len(rows) > 5 or len(set(r.get("ticker") for r in rows)) != len(rows):
            issues.append("PMR80_INVALID_RANKING")
        if any(str(r.get("prediction_label", "")).startswith("PREDICTED_BULLISH") for r in rows):
            issues.append("PMR80_LEGACY_LABEL")
        times = []
        for row in rows:
            raw = row.get("generated_at")
            if raw:
                times.append(dt.datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(UTC))
        if not times:
            issues.append("PMR80_MISSING_TIMESTAMP")
        else:
            result["last_publish"] = max(times).isoformat()
            result["publish_age_minutes"] = round((now - max(times)).total_seconds() / 60, 1)
    except (urllib.error.URLError, ValueError, KeyError) as exc:
        issues.append("SUPABASE_QUERY_FAILED")
        result["error"] = str(exc)[:250]
    # Market-session-aware auto recovery: do not repeatedly trigger outside market hours.
    weekday = local.weekday() < 5
    clock = local.hour * 60 + local.minute
    market_window = weekday and 8 * 60 + 35 <= clock <= 16 * 60 + 15
    stale = result.get("publish_age_minutes", 999999) > 45
    repairable = market_window and (stale or "PMR80_EMPTY" in issues or "PMR80_LEGACY_LABEL" in issues)
    result["recovery_needed"] = bool(repairable)
    print(json.dumps(result, ensure_ascii=False))
    if repairable and os.environ.get("GITHUB_TOKEN") and os.environ.get("GITHUB_REPOSITORY"):
        repo = os.environ["GITHUB_REPOSITORY"]
        gh = {"Authorization": "Bearer " + os.environ["GITHUB_TOKEN"], "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
        # Prevent repeated dispatches while a scanner is queued or running.
        url = "https://api.github.com/repos/" + repo + "/actions/workflows/hanz-swing-engine.yml/runs?per_page=10"
        try:
            runs = request(url, gh).get("workflow_runs", [])
            recent = [r for r in runs if r.get("status") in ("queued", "in_progress") or (
                r.get("created_at") and (now - dt.datetime.fromisoformat(r["created_at"].replace("Z", "+00:00"))).total_seconds() < 15 * 60)]
            if not recent:
                req = urllib.request.Request("https://api.github.com/repos/" + repo + "/actions/workflows/hanz-swing-engine.yml/dispatches", data=json.dumps({"ref": "main"}).encode(), headers={**gh, "Content-Type": "application/json"}, method="POST")
                with urllib.request.urlopen(req, timeout=20) as response:
                    result["recovery_dispatch_status"] = response.status
            else:
                result["recovery"] = "scanner already running or recently triggered"
        except (urllib.error.URLError, ValueError) as exc:
            result["recovery_error"] = str(exc)[:250]
    print("HANZ WATCHDOG FINAL: " + json.dumps(result))
    if issues:
        print("::warning::HANZ watchdog issues: " + ", ".join(issues))

if __name__ == "__main__":
    main()
