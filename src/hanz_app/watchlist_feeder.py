import json
import math
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


# ============================================================
# HANZ AUTO WATCHLIST FEEDER v6
# Structure-specific + BUY/SL sanity guards
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


def round_price(value):
    if value is None:
        return None

    return round(
        float(value),
        4,
    )


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
# EXTRACT REAL BEI CANDIDATES
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
# LEVEL BUILDING WITH SANITY GUARDS
# ============================================================

def build_levels(row):
    technical = row.get(
        "technical",
        {},
    )

    if not isinstance(
        technical,
        dict,
    ):
        technical = {}

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

    if signal_close is None:
        raise RuntimeError(
            "Candidate missing signal_close"
        )

    # -------------------------
    # ENTRY ZONE
    # -------------------------

    if (
        atr is not None
        and atr > 0
    ):
        entry_low = (
            signal_close
            - (0.25 * atr)
        )

        entry_high = (
            signal_close
            + (0.25 * atr)
        )

    else:
        # fallback ±0.5%
        entry_low = (
            signal_close * 0.995
        )

        entry_high = (
            signal_close * 1.005
        )

    entry_low = max(
        0,
        entry_low,
    )

    # -------------------------
    # CONFIRMATION
    # Must be >= entry_high
    # -------------------------

    possible_confirmation = [
        value
        for value in [
            resistance,
            signal_close,
            entry_high,
        ]
        if value is not None
    ]

    confirmation_price = max(
        possible_confirmation
    )

    # Small buffer above entry zone
    # if resistance is too low.
    minimum_confirmation = (
        entry_high * 1.001
    )

    if (
        confirmation_price
        < minimum_confirmation
    ):
        confirmation_price = (
            minimum_confirmation
        )

    # -------------------------
    # INVALIDATION
    # Must be < entry_low
    # -------------------------

    invalidation_price = None

    if (
        support is not None
        and support < entry_low
    ):
        invalidation_price = support

    elif (
        atr is not None
        and atr > 0
    ):
        invalidation_price = (
            entry_low
            - (1.25 * atr)
        )

    else:
        # fallback 3% under entry_low
        invalidation_price = (
            entry_low * 0.97
        )

    invalidation_price = max(
        0,
        invalidation_price,
    )

    # Final hard sanity guard.
    if invalidation_price >= entry_low:

        if (
            atr is not None
            and atr > 0
        ):
            invalidation_price = (
                entry_low
                - (1.5 * atr)
            )

        else:
            invalidation_price = (
                entry_low * 0.97
            )

    if confirmation_price <= entry_high:
        confirmation_price = (
            entry_high * 1.001
        )

    return {
        "signal_close": round_price(
            signal_close
        ),
        "entry_low": round_price(
            entry_low
        ),
        "entry_high": round_price(
            entry_high
        ),
        "confirmation_price": round_price(
            confirmation_price
        ),
        "invalidation_price": round_price(
            invalidation_price
        ),
        "atr": round_price(
            atr
        ),
    }


# ============================================================
# BUILD WATCHLIST ROW
# ============================================================

def build_watchlist_row(
    candidate,
):
    row = candidate["raw"]

    levels = build_levels(
        row
    )

    priority = calculate_priority(
        row,
        candidate["index"],
    )

    return {
        "ticker": candidate["ticker"],
        "source": SOURCE_NAME,
        "priority": priority,
        "entry_zone_low": (
            levels["entry_low"]
        ),
        "entry_zone_high": (
            levels["entry_high"]
        ),
        "confirmation_price": (
            levels[
                "confirmation_price"
            ]
        ),
        "invalidation_price": (
            levels[
                "invalidation_price"
            ]
        ),
        "reason": build_reason(
            row
        ),
        "updated_at": now_iso(),
    }


# ============================================================
# UPSERT
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
            "select": (
                "ticker,source"
            ),
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


def delete_ticker(ticker):
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
        "Feeder v6 started.",
        flush=True,
    )

    scan = load_scan()

    candidates = extract_candidates(
        scan
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

        try:
            row = build_watchlist_row(
                candidate
            )

        except Exception as exc:

            print(
                f"Candidate "
                f"{candidate['ticker']} "
                f"skipped: {exc}",
                flush=True,
            )

            continue

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

    if not rows:

        print(
            "No sane candidates "
            "to publish.",
            flush=True,
        )

        return

    upsert_watchlist(
        rows
    )

    remove_stale_auto_rows(
        [
            row["ticker"]
            for row in rows
        ]
    )

    print(
        "HANZ Auto Watchlist "
        "Feeder v6 completed.",
        flush=True,
    )


if __name__ == "__main__":
    main()
