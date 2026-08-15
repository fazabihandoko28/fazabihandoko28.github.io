import os
import subprocess
import time
from datetime import datetime, timezone


SCAN_INTERVAL = int(os.getenv("HANZ_SCAN_INTERVAL", "900"))  # default 15 menit


def run(command):
    print(f"\n[{datetime.now(timezone.utc).isoformat()}] RUN: {' '.join(command)}", flush=True)
    subprocess.run(command, check=True)


def run_cycle():
    print("\n========== HANZ CYCLE START ==========", flush=True)

    # 1. Build Dynamic Top 100 BEI
    run([
        "python", "-m", "hanz_app.build_liquid_universe",
        "--pool", "config/universe/bei_candidate_pool.csv",
        "--output", "artifacts/universe/bei_top100.csv",
        "--metrics", "artifacts/universe/bei_liquidity_metrics.json",
        "--target", "100",
        "--period", "6mo",
        "--lookback", "60",
    ])

    # 2. Scan Dynamic Top 100
    run([
        "python", "-m", "hanz_app.paper_scan",
        "--universe", "artifacts/universe/bei_top100.csv",
        "--markets", "BEI",
        "--period", "1y",
        "--interval", "1d",
        "--candidate-limit", "5",
        "--output", "artifacts/paper_scans/latest.json",
    ])

    # 3. Update paper-trading journal
    run([
        "python", "-m", "hanz_app.update_journal",
        "--scan", "artifacts/paper_scans/latest.json",
        "--journal", "artifacts/paper_trading/journal.json",
    ])

    # 4. Render dashboard
    run([
        "python", "-m", "hanz_app.render_report",
        "--input", "artifacts/paper_scans/latest.json",
        "--output", "dashboard/index.html",
    ])

    # 5. Publish lean dashboard data
    run([
        "python", "tools/publish_scan_results.py",
        "--scan", "artifacts/paper_scans/latest.json",
        "--report", "dashboard/index.html",
    ])

    # 6. Foundation decisions
    run([
        "python", "tools/integrate_foundation.py",
        "--input", "artifacts/paper_scans/latest.json",
        "--output", "dashboard/data/decisions.json",
    ])

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
