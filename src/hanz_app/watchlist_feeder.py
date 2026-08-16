import json
import math
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


# ============================================================
# HANZ AUTO WATCHLIST FEEDER v5
# Structure-specific for paper_scan output:
#
# scan
# └── markets[]
#     └── candidates[]
#         ├── symbol
#         ├── tier
#         ├── entry_status
#         ├── selection_reasons
#         ├── signal_close
#         └── technical
#             ├── resistance20
#             ├── support20
#             ├── atr14
#             └── ...
# ============================================================


SUPABASE_URL = os.getenv(
    "SUPABASE_URL",
    "",
).rstrip("/")

SUPABASE_SECRET_KEY = os.getenv(
    "SUPABASE_SECRET_KEY",
    "",
)

SCAN_PATH = Path(
    "artifacts/paper_scans/latest.json"
)

MAX_CANDIDATES = int(
    os.getenv(
        "HANZ_WATCHLIST_MAX_CANDIDATES",
        "5",
    )
)

SOURCE_NAME = "AUTO_SLOW_ENGINE"


# ============================================================
# HELPERS
# ============================================================


def now_iso():
    return datetime.now(
        timezone.utc
    ).isoformat()


def safe_float(value):
    try:
        if value is None:
            return None

        number = float(value)

        if math.isnan(number):
            return None

        return number

    except Exception:
        return None


def clean_ticker(value):
    if value is None:
        return None

    ticker = str(
        value
    ).strip().upper()

    if ticker.endswith(".JK"):
        ticker = ticker[:-3]

    return ticker or None


# ============================================================
# SUPABASE
# ============================================================


def supabase_request(
    method,
    endpoint,
    payload=None,
    prefer=None,
):
    if not SUPABASE_URL:
        raise RuntimeError(
            "SUPABASE_URL missing"
        )

    if not SUPABASE_SECRET_KEY:
        raise RuntimeError(
            "SUPABASE_SECRET_KEY missing"
        )

    url = (
        f"{SUPABASE_URL}"
        f"/rest/v1/"
        f"{endpoint}"
    )

    headers = {
        "apikey": SUPABASE_SECRET_KEY,
        "Authorization": (
            f"Bearer "
            f"{SUPABASE_SECRET_KEY}"
        ),
        "Content-Type": "application/json",
    }

    if prefer:
        headers["Prefer"] = prefer

    body = None

    if payload is not None:
        body = json.dumps(
            payload,
            default=str,
        ).encode("utf-8")

    request = urllib.request.Request(
        url,
        data=body,
        method=method,
        headers=headers,
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=30,
        ) as response:

            raw = response.read()

            if not raw:
                return None

            return json.loads(
                raw.decode("utf-8")
            )

    except urllib.error.HTTPError as exc:

        detail = exc.read().decode(
            "utf-8",
            errors="replace",
        )

        raise RuntimeError(
            f"Supabase HTTP "
            f"{exc.code}: "
            f"{detail}"
        ) from exc


# ============================================================
# LOAD SCAN
# ============================================================


def load_scan():
    if not SCAN_PATH.exists():
        raise FileNotFoundError(
            f"Scan file not found: "
            f"{SCAN_PATH}"
        )

    with open(
        SCAN_PATH,
        "r",
        encoding="utf-8",
    ) as f:

        return json.load(f)


# ============================================================
# EXTRACT REAL PAPER-SCAN CANDIDATES
# ============================================================


def extract_candidates(scan):
    if not isinstance(scan, dict):
        raise RuntimeError(
            "paper_scan root is not a dict"
        )

    markets = scan.get(
        "markets"
    )

    if not isinstance(markets, list):
        raise RuntimeError(
            "paper_scan markets is not a list"
        )

    found = []

    for market_block in markets:

        if not isinstance(
            market_block,
            dict,
        ):
            continue

        market_name = str(
            market_block.get(
                "market",
                "",
            )
        ).upper()

        if market_name != "BEI":
            continue

        rows = market_block.get(
            "candidates",
            [],
        )

        if not isinstance(
            rows,
            list,
        ):
            continue

        print(
            f"BEI paper candidates: "
            f"{len(rows)}",
            flush=True,
        )

        for index, row in enumerate(
            rows
        ):

            if not isinstance(
                row,
                dict,
            ):
                continue

            symbol = clean_ticker(
                row.get("symbol")
            )

            if not symbol:
                continue

            found.append(
                {
                    "ticker": symbol,
                    "raw": row,
                    "index": index,
                }
            )

    return found[
        :MAX_CANDIDATES
    ]


# ============================================================
# PRIORITY
# ============================================================


def calculate_priority(
    row,
    index,
):
    score = 50

    reasons = row.get(
        "selection_reasons",
        [],
    )

    if isinstance(
        reasons,
        list,
    ):
        score += min(
            len(reasons) * 5,
            25,
        )

    tier = str(
        row.get(
            "tier",
            "",
        )
    ).upper()

    if tier == "PRIMARY":
        score += 15

    elif tier == "SECONDARY":
        score += 8

    status = str(
        row.get(
            "entry_status",
            "",
        )
    ).upper()

    if status in {
        "READY",
        "WATCH",
    }:
        score += 5

    # Earlier slow-engine candidates
    # retain slightly higher priority.
    score += max(
        0,
        5 - index,
    )

    return max(
        0,
        min(
            100,
            int(score),
        ),
    )


# ============================================================
# REASON
# ============================================================


def build_reason(row):
    parts = []

    tier = row.get("tier")

    if tier:
        parts.append(
            f"Tier: {tier}"
        )

    status = row.get(
        "entry_status"
    )

    if status:
        parts.append(
            f"Entry: {status}"
        )

    reasons = row.get(
        "selection_reasons",
        [],
    )

    if isinstance(
        reasons,
        list,
    ):
        clean_reasons = [
            str(reason).strip()
            for reason in reasons
            if str(reason).strip()
        ]

        if clean_reasons:
            parts.append(
                " | ".join(
                    clean_reasons[:6]
                )
            )

    if not parts:
        return (
            "Auto-selected by "
            "HANZ slow engine"
        )

    return " | ".join(parts)


# ============================================================
# BUILD WATCHLIST ROW
# ============================================================


def build_watchlist_row(
    candidate,
):
    row = candidate["raw"]

    technical = row.get(
        "technical",
        {},
    )

    if not isinstance(
        technical,
        dict,
    ):
        technical = {}

    ticker = candidate["ticker"]

    signal_close = safe_float(
        row.get(
            "signal_close"
        )
    )

    resistance = safe_float(
        technical.get(
            "resistance20"
        )
    )

    support = safe_float(
        technical.get(
            "support20"
        )
    )

    atr = safe_float(
        technical.get(
            "atr14"
        )
    )

    # BUY confirmation:
    # Prefer actual 20-bar resistance.
    # Fast Engine requires price to break
    # above this level plus 1m/5m confirmation.
    confirmation_price = (
        resistance
        if resistance is not None
        else signal_close
    )

    # Risk invalidation:
    # Prefer technical support.
    invalidation_price = support

    entry_low = None
    entry_high = None

    # Small reference zone around signal close.
    if (
        signal_close is not None
        and atr is not None
        and atr > 0
    ):
        entry_low = round(
            max(
                0,
                signal_close
                - (0.25 * atr),
            ),
            4,
        )

        entry_high = round(
            signal_close
            + (0.25 * atr),
            4,
        )

    priority = calculate_priority(
        row,
        candidate["index"],
    )

    return {
        "ticker": ticker,
        "source": SOURCE_NAME,
        "priority": priority,
        "entry_zone_low": entry_low,
        "entry_zone_high": entry_high,
        "confirmation_price": (
            confirmation_price
        ),
        "invalidation_price": (
            invalidation_price
        ),
        "reason": build_reason(
            row
        ),
        "updated_at": now_iso(),
    }


# ============================================================
# UPSERT CURRENT CANDIDATES
# ============================================================


def upsert_watchlist(rows):
    if not rows:

        print(
            "No candidates to publish.",
            flush=True,
        )

        return

    supabase_request(
        "POST",
        (
            "hanz_watchlist"
            "?on_conflict=ticker"
        ),
        rows,
        prefer=(
            "resolution=merge-duplicates,"
            "return=minimal"
        ),
    )

    print(
        f"Published "
        f"{len(rows)} candidate(s) "
        f"to hanz_watchlist.",
        flush=True,
    )


# ============================================================
# REMOVE OLD AUTO CANDIDATES
# ============================================================


def fetch_existing_auto_rows():
    query = urllib.parse.urlencode(
        {
            "select": "ticker,source",
            "source": (
                f"eq.{SOURCE_NAME}"
            ),
        }
    )

    rows = supabase_request(
        "GET",
        f"hanz_watchlist?{query}",
    )

    return rows or []


def delete_ticker(
    ticker,
):
    encoded = urllib.parse.quote(
        str(ticker),
        safe="",
    )

    supabase_request(
        "DELETE",
        (
            "hanz_watchlist"
            f"?ticker=eq.{encoded}"
            f"&source=eq.{SOURCE_NAME}"
        ),
        prefer="return=minimal",
    )


def remove_stale_auto_rows(
    current_tickers,
):
    existing = (
        fetch_existing_auto_rows()
    )

    current = {
        clean_ticker(ticker)
        for ticker in current_tickers
    }

    removed = []

    for row in existing:

        ticker = clean_ticker(
            row.get("ticker")
        )

        if not ticker:
            continue

        if ticker not in current:

            delete_ticker(
                ticker
            )

            removed.append(
                ticker
            )

    if removed:
        print(
            "Removed stale AUTO "
            "watchlist rows: "
            + ", ".join(removed),
            flush=True,
        )


# ============================================================
# MAIN
# ============================================================


def main():
    print(
        "HANZ Auto Watchlist "
        "Feeder v5 started.",
        flush=True,
    )

    scan = load_scan()

    candidates = (
        extract_candidates(
            scan
        )
    )

    print(
        f"Valid BEI candidates found: "
        f"{len(candidates)}",
        flush=True,
    )

    if not candidates:

        print(
            "No valid BEI candidates "
            "to publish.",
            flush=True,
        )

        return

    rows = []

    for candidate in candidates:

        row = build_watchlist_row(
            candidate
        )

        rows.append(
            row
        )

        print(
            f"Candidate: "
            f"{row['ticker']} | "
            f"priority="
            f"{row['priority']} | "
            f"entry="
            f"{row['entry_zone_low']}"
            f"-"
            f"{row['entry_zone_high']} | "
            f"confirm="
            f"{row['confirmation_price']} | "
            f"invalid="
            f"{row['invalidation_price']}",
            flush=True,
        )

    # First publish current candidates.
    upsert_watchlist(
        rows
    )

    # Then remove old AUTO candidates
    # no longer selected by slow engine.
    remove_stale_auto_rows(
        [
            row["ticker"]
            for row in rows
        ]
    )

    print(
        "HANZ Auto Watchlist "
        "Feeder v5 completed.",
        flush=True,
    )


if __name__ == "__main__":
    main()
