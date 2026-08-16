import json
import os
import subprocess
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


SCAN_INTERVAL = int(os.getenv("HANZ_SCAN_INTERVAL", "900"))
RETRY_INTERVAL = int(os.getenv("HANZ_RETRY_INTERVAL", "60"))
HEARTBEAT_INTERVAL = int(os.getenv("HANZ_HEARTBEAT_INTERVAL", "60"))

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_SECRET_KEY = os.getenv("SUPABASE_SECRET_KEY", "")

STATE_ID = "bei-main"

JOURNAL_PATH = Path("artifacts/paper_trading/journal.json")
SCAN_PATH = Path("artifacts/paper_scans/latest.json")
DECISIONS_PATH = Path("dashboard/data/decisions.json")
DASHBOARD_PATH = Path("dashboard/index.html")

worker_started_at = datetime.now(timezone.utc).isoformat()

consecutive_failures = 0
intraday_health_done = False

stop_event = threading.Event()


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def run(command):
    print(
        f"\n[{now_iso()}] RUN: {' '.join(command)}",
        flush=True,
    )

    subprocess.run(
        command,
        check=True,
    )


def read_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path, data):
    path = Path(path)

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with open(
        path,
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2,
        )


def supabase_request(
    method,
    endpoint,
    payload=None,
    prefer=None,
):
    if not SUPABASE_URL or not SUPABASE_SECRET_KEY:
        raise RuntimeError(
            "Supabase environment variables are missing"
        )

    url = (
        f"{SUPABASE_URL}/rest/v1/"
        f"{endpoint}"
    )

    body = None

    headers = {
        "apikey": SUPABASE_SECRET_KEY,
        "Content-Type": "application/json",
    }

    if prefer:
        headers["Prefer"] = prefer

    if payload is not None:
        body = json.dumps(
            payload
        ).encode("utf-8")

    request = urllib.request.Request(
        url,
        data=body,
        method=method,
        headers=headers,
    )

    with urllib.request.urlopen(
        request,
        timeout=30,
    ) as response:

        raw = response.read()

        if raw:
            return json.loads(
                raw.decode("utf-8")
            )

        return None


def restore_state():

    print(
        "Restoring HANZ persistent state from Supabase...",
        flush=True,
    )

    query = urllib.parse.urlencode(
        {
            "id": f"eq.{STATE_ID}",
            "select": (
                "journal,"
                "last_success_at,"
                "last_error,"
                "consecutive_failures"
            ),
        }
    )

    rows = supabase_request(
        "GET",
        f"hanz_live_state?{query}",
    )

    if not rows:
        print(
            "No previous Supabase state found.",
            flush=True,
        )
        return

    state = rows[0]

    journal = state.get("journal")

    if journal:

        write_json(
            JOURNAL_PATH,
            journal,
        )

        print(
            f"Journal restored to {JOURNAL_PATH}",
            flush=True,
        )

    print(
        "Previous last_success_at:",
        state.get("last_success_at"),
        flush=True,
    )

    print(
        "Previous consecutive_failures:",
        state.get(
            "consecutive_failures",
            0,
        ),
        flush=True,
    )


def update_health(
    *,
    heartbeat=True,
    success=False,
    error=None,
    failure_count=None,
):

    payload = {
        "id": STATE_ID,
        "status": "online",
        "worker_started_at": worker_started_at,
    }

    if heartbeat:
        payload["heartbeat_at"] = now_iso()

    if success:
        payload["last_success_at"] = now_iso()
        payload["last_error"] = None
        payload["consecutive_failures"] = 0

    if error is not None:
        payload["last_error"] = str(error)

    if failure_count is not None:
        payload[
            "consecutive_failures"
        ] = failure_count

    supabase_request(
        "POST",
        "hanz_live_state?on_conflict=id",
        payload,
        prefer=(
            "resolution=merge-duplicates,"
            "return=minimal"
        ),
    )


def heartbeat_loop():

    while not stop_event.is_set():

        try:

            update_health(
                heartbeat=True
            )

            print(
                f"[{now_iso()}] Heartbeat OK",
                flush=True,
            )

        except Exception as exc:

            print(
                f"[{now_iso()}] "
                f"Heartbeat failed: {exc}",
                flush=True,
            )

        stop_event.wait(
            HEARTBEAT_INTERVAL
        )


def build_universe():

    print(
        "\n========== BUILD DYNAMIC TOP 100 ==========",
        flush=True,
    )

    run([
        "python",
        "-m",
        "hanz_app.build_liquid_universe",

        "--pool",
        "config/universe/bei_candidate_pool.csv",

        "--output",
        "artifacts/universe/bei_top100.csv",

        "--metrics",
        "artifacts/universe/bei_liquidity_metrics.json",

        "--target",
        "100",

        "--period",
        "6mo",

        "--lookback",
        "60",
    ])


def run_intraday_health_test():

    global intraday_health_done

    if intraday_health_done:
        return

    universe = Path(
        "artifacts/universe/bei_top100.csv"
    )

    if not universe.exists():

        print(
            "Intraday health skipped: "
            "Top 100 universe not ready.",
            flush=True,
        )

        return

    print(
        "\n========== INTRADAY DATA HEALTH TEST ==========",
        flush=True,
    )

    try:

        run([
            "python",
            "-m",
            "hanz_app.intraday_health",
        ])

        intraday_health_done = True

        print(
            "Intraday health test completed.",
            flush=True,
        )

    except Exception as exc:

        print(
            f"Intraday health test failed: {exc}",
            flush=True,
        )

    print(
        "========== INTRADAY HEALTH END ==========\n",
        flush=True,
    )


def publish_to_supabase():

    scan_data = read_json(
        SCAN_PATH
    )

    decisions = read_json(
        DECISIONS_PATH
    )

    journal = read_json(
        JOURNAL_PATH
    )

    with open(
        DASHBOARD_PATH,
        "r",
        encoding="utf-8",
    ) as f:

        rendered_html = f.read()

    payload = {

        "id": STATE_ID,

        "updated_at": now_iso(),

        "market": "BEI",

        "status": "online",

        "scan_data": scan_data,

        "decisions": decisions,

        "journal": journal,

        "rendered_html": rendered_html,

        "heartbeat_at": now_iso(),

        "last_success_at": now_iso(),

        "last_error": None,

        "consecutive_failures": 0,

        "worker_started_at": worker_started_at,
    }

    supabase_request(
        "POST",
        "hanz_live_state?on_conflict=id",
        payload,
        prefer=(
            "resolution=merge-duplicates,"
            "return=minimal"
        ),
    )

    print(
        "Supabase live publish OK",
        flush=True,
    )


def run_cycle():

    print(
        "\n========== HANZ CYCLE START ==========",
        flush=True,
    )

    # 1. BUILD TOP 100
    build_universe()

    # 2. TEST INTRADAY DATA
    # only once per Railway startup
    run_intraday_health_test()

    # 3. MAIN SCAN
    run([
        "python",
        "-m",
        "hanz_app.paper_scan",

        "--universe",
        "artifacts/universe/bei_top100.csv",

        "--markets",
        "BEI",

        "--period",
        "1y",

        "--interval",
        "1d",

        "--candidate-limit",
        "5",

        "--output",
        str(SCAN_PATH),
    ])

    # 4. JOURNAL
    run([
        "python",
        "-m",
        "hanz_app.update_journal",

        "--scan",
        str(SCAN_PATH),

        "--journal",
        str(JOURNAL_PATH),
    ])

    # 5. DASHBOARD
    run([
        "python",
        "-m",
        "hanz_app.render_report",

        "--input",
        str(SCAN_PATH),

        "--output",
        str(DASHBOARD_PATH),
    ])

    # 6. DASHBOARD DATA
    run([
        "python",
        "tools/publish_scan_results.py",

        "--scan",
        str(SCAN_PATH),

        "--report",
        str(DASHBOARD_PATH),
    ])

    # 7. DECISION ENGINE
    run([
        "python",
        "tools/integrate_foundation.py",

        "--input",
        str(SCAN_PATH),

        "--output",
        str(DECISIONS_PATH),
    ])

    # 8. PERSIST TO SUPABASE
    publish_to_supabase()

    print(
        "========== HANZ CYCLE COMPLETE ==========\n",
        flush=True,
    )


def main():

    global consecutive_failures

    print(
        "HANZ Railway Worker started.",
        flush=True,
    )

    print(
        f"Scan interval: {SCAN_INTERVAL} seconds",
        flush=True,
    )

    print(
        f"Retry interval: {RETRY_INTERVAL} seconds",
        flush=True,
    )

    print(
        f"Heartbeat interval: {HEARTBEAT_INTERVAL} seconds",
        flush=True,
    )

    # RESTORE MEMORY

    try:

        restore_state()

    except Exception as exc:

        print(
            f"State restore failed: {exc}",
            flush=True,
        )

    # WATCHDOG

    heartbeat_thread = threading.Thread(
        target=heartbeat_loop,
        daemon=True,
    )

    heartbeat_thread.start()

    # 24/7 LOOP

    while True:

        try:

            run_cycle()

            consecutive_failures = 0

            try:

                update_health(
                    heartbeat=True,
                    success=True,
                )

            except Exception as exc:

                print(
                    f"Health update failed: {exc}",
                    flush=True,
                )

            print(
                f"Sleeping {SCAN_INTERVAL} seconds...",
                flush=True,
            )

            time.sleep(
                SCAN_INTERVAL
            )

        except Exception as exc:

            consecutive_failures += 1

            print(
                f"HANZ cycle failed "
                f"(#{consecutive_failures}): "
                f"{exc}",
                flush=True,
            )

            try:

                update_health(
                    heartbeat=True,
                    error=exc,
                    failure_count=consecutive_failures,
                )

            except Exception as health_exc:

                print(
                    "Failure health update failed: "
                    f"{health_exc}",
                    flush=True,
                )

            print(
                f"Retrying in {RETRY_INTERVAL} seconds...",
                flush=True,
            )

            time.sleep(
                RETRY_INTERVAL
            )


if __name__ == "__main__":
    main()
