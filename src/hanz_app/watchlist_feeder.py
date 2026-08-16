import json
import os
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_SECRET_KEY = os.getenv("SUPABASE_SECRET_KEY", "")

SCAN_PATH = Path("artifacts/paper_scans/latest.json")

MAX_CANDIDATES = int(
    os.getenv("HANZ_WATCHLIST_MAX_CANDIDATES", "5")
)


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def clean_ticker(ticker):
    ticker = str(ticker).strip().upper()

    if ticker.endswith(".JK"):
        ticker = ticker[:-3]

    return ticker


def supabase_request(
    method,
    endpoint,
    payload=None,
    prefer=None,
):
    if not SUPABASE_URL:
        raise RuntimeError("SUPABASE_URL missing")

    if not SUPABASE_SECRET_KEY:
        raise RuntimeError("SUPABASE_SECRET_KEY missing")

    url = f"{SUPABASE_URL}/rest/v1/{endpoint}"

    headers = {
        "apikey": SUPABASE_SECRET_KEY,
        "Content-Type": "application/json",
    }

    if prefer:
        headers["Prefer"] = prefer

    body = None

    if payload is not None:
        body = json.dumps(payload).encode("utf-8")

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

        if not raw:
            return None

        return json.loads(raw.decode("utf-8"))


def load_scan():
    if not SCAN_PATH.exists():
        raise FileNotFoundError(
            f"Scan file not found: {SCAN_PATH}"
        )

    with open(
        SCAN_PATH,
        "r",
        encoding="utf-8",
    ) as f:
        return json.load(f)


def extract_candidates(scan):
    candidates = []

    possible_lists = [
        scan.get("candidates"),
        scan.get("signals"),
        scan.get("results"),
        scan.get("opportunities"),
    ]

    source = None

    for item in possible_lists:
        if isinstance(item, list):
            source = item
            break

    if source is None:
        return []

    for row in source:
        if not isinstance(row, dict):
            continue

        ticker = (
            row.get("ticker")
            or row.get("symbol")
            or row.get("code")
        )

        if not ticker:
            continue

        score = (
            row.get("score")
            or row.get("confidence")
            or row.get("rank")
            or 0
        )

        try:
            score = float(score)
        except Exception:
            score = 0

        candidates.append(
            {
                "ticker": clean_ticker(ticker),
                "score": score,
                "raw": row,
            }
        )

    candidates.sort(
        key=lambda x: x["score"],
        reverse=True,
    )

    return candidates[:MAX_CANDIDATES]


def build_watchlist_row(candidate):
    row = candidate["raw"]

    ticker = candidate["ticker"]

    confirmation_price = (
        row.get("confirmation_price")
        or row.get("breakout_price")
        or row.get("entry_price")
        or row.get("price")
    )

    invalidation_price = (
        row.get("invalidation_price")
        or row.get("stop_loss")
    )

    entry_low = (
        row.get("entry_zone_low")
        or row.get("entry_low")
    )

    entry_high = (
        row.get("entry_zone_high")
        or row.get("entry_high")
    )

    reason = (
        row.get("reason")
        or row.get("thesis")
        or row.get("signal")
        or "Auto-selected by HANZ slow engine"
    )

    return {
        "ticker": ticker,
        "source": "AUTO_SLOW_ENGINE",
        "priority": int(
            round(candidate["score"])
        ),
        "entry_zone_low": entry_low,
        "entry_zone_high": entry_high,
        "confirmation_price": confirmation_price,
        "invalidation_price": invalidation_price,
        "reason": reason,
        "updated_at": now_iso(),
    }


def upsert_watchlist(rows):
    if not rows:
        print(
            "No candidates to publish.",
            flush=True,
        )
        return

    supabase_request(
        "POST",
        "hanz_watchlist?on_conflict=ticker",
        rows,
        prefer=(
            "resolution=merge-duplicates,"
            "return=minimal"
        ),
    )

    print(
        f"Published {len(rows)} candidate(s) "
        f"to hanz_watchlist.",
        flush=True,
    )


def main():
    scan = load_scan()

    candidates = extract_candidates(scan)

    print(
        f"Auto-watchlist candidates found: "
        f"{len(candidates)}",
        flush=True,
    )

    rows = [
        build_watchlist_row(candidate)
        for candidate in candidates
    ]

    for row in rows:
        print(
            f"Candidate: "
            f"{row['ticker']} | "
            f"priority={row['priority']} | "
            f"confirmation={row['confirmation_price']}",
            flush=True,
        )

    upsert_watchlist(rows)


if __name__ == "__main__":
    main()
