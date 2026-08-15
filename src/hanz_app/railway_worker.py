import json
import os
import subprocess
import time
import urllib.request
from datetime import datetime, timezone


SCAN_INTERVAL = int(os.getenv("HANZ_SCAN_INTERVAL", "900"))

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_SECRET_KEY = os.getenv("SUPABASE_SECRET_KEY", "")


def run(command):
    print(
        f"\n[{datetime.now(timezone.utc).isoformat()}] RUN: {' '.join(command)}",
        flush=True,
    )
    subprocess.run(command, check=True)


def read_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def publish_to_supabase():
    if not SUPABASE_URL or not SUPABASE_SECRET_KEY:
        print("Supabase variables missing — skipping live publish.", flush=True)
        return

    scan_data = read_json("artifacts/paper_scans/latest.json")
    decisions = read_json("dashboard/data/decisions.json")
    journal = read_json("artifacts/paper_trading/journal.json")

    with open("dashboard/index.html", "r", encoding="utf-8") as f:
        rendered_html = f.read()

    payload = {
        "id": "bei-main",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "market": "BEI",
        "status": "online",
        "scan_data": scan_data,
        "decisions": decisions,
        "journal": journal,
        "rendered_html": rendered_html,
    }

    body = json.dumps(payload).encode("utf-8")

    url = (
        f"{SUPABASE_URL}/rest/v1/hanz_live_state"
        "?on_conflict=id"
    )

    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "apikey": SUPABASE_SECRET_KEY,
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates,return=minimal",
        },
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        print(
            f"Supabase live publish OK: HTTP {response.status}",
            flush=True,
        )


def run_cycle():
    print("\n========== HANZ CYCLE START ==========", flush=True)

    run([
        "python", "-m", "hanz_app.build_liquid_universe",
        "--pool", "config/universe/bei_candidate_pool.csv",
        "--output", "artifacts/universe/bei_top100.csv",
        "--metrics", "artifacts/universe/bei_liquidity_metrics.json",
        "--target", "100",
        "--period", "6mo",
        "--lookback", "60",
    ])

    run([
        "python", "-m", "hanz_app.paper_scan",
        "--universe", "artifacts/universe/bei_top100.csv",
        "--markets", "BEI",
        "--period", "1y",
        "--interval", "1d",
        "--candidate-limit", "5",
        "--output", "artifacts/paper_scans/latest.json",
    ])

    run([
        "python", "-m", "hanz_app.update_journal",
        "--scan", "artifacts/paper_scans/latest.json",
        "--journal", "artifacts/paper_trading/journal.json",
    ])

    run([
        "python", "-m", "hanz_app.render_report",
        "--input", "artifacts/paper_scans/latest.json",
        "--output", "dashboard/index.html",
    ])

    run([
        "python", "tools/publish_scan_results.py",
        "--scan", "artifacts/paper_scans/latest.json",
        "--report", "dashboard/index.html",
    ])

    run([
        "python", "tools/integrate_foundation.py",
        "--input", "artifacts/paper_scans/latest.json",
        "--output", "dashboard/data/decisions.json",
    ])

    publish_to_supabase()

    print("========== HANZ CYCLE COMPLETE ==========\n", flush=True)


def main():
    print("HANZ Railway Worker started.", flush=True)
    print(f"Scan interval: {SCAN_INTERVAL} seconds", flush=True)

    while True:
        try:
            run_cycle()
        except Exception as exc:
            print(f"HANZ cycle failed: {exc}", flush=True)

        print(f"Sleeping {SCAN_INTERVAL} seconds...", flush=True)
        time.sleep(SCAN_INTERVAL)


if __name__ == "__main__":
    main()
