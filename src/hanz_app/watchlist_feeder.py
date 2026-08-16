import json
import math
import os
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


# ============================================================
# HANZ AUTO WATCHLIST FEEDER v3
# ============================================================

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_SECRET_KEY = os.getenv("SUPABASE_SECRET_KEY", "")

SCAN_PATH = Path("artifacts/paper_scans/latest.json")

MAX_CANDIDATES = int(
    os.getenv(
        "HANZ_WATCHLIST_MAX_CANDIDATES",
        "5",
    )
)

SOURCE_NAME = "AUTO_SLOW_ENGINE"


# ============================================================
# BASIC HELPERS
# ============================================================

def now_iso():
    return datetime.now(timezone.utc).isoformat()


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

    ticker = str(value).strip().upper()

    if ticker.endswith(".JK"):
        ticker = ticker[:-3]

    return ticker.strip() or None


def looks_like_idx_ticker(value):
    ticker = clean_ticker(value)

    if not ticker:
        return False

    # IDX ticker normally 4 characters.
    # We allow 3-6 alphanumeric characters
    # to tolerate special securities.
    if not re.fullmatch(
        r"[A-Z0-9]{3,6}",
        ticker,
    ):
        return False

    blocked = {
        "BEI",
        "IDX",
        "MARKET",
        "MARKETS",
        "BUY",
        "SELL",
        "HOLD",
        "OPEN",
        "CLOSE",
        "TRUE",
        "FALSE",
        "NULL",
        "NONE",
        "SIGNAL",
        "RESULT",
    }

    return ticker not in blocked


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
            f"Bearer {SUPABASE_SECRET_KEY}"
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
# LOAD PAPER SCAN
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
# TICKER / SCORE DISCOVERY
# ============================================================

def extract_ticker_from_row(row):
    if not isinstance(row, dict):
        return None

    keys = [
        "ticker",
        "symbol",
        "code",
        "stock",
        "stock_code",
        "security",
        "security_code",
    ]

    for key in keys:
        value = row.get(key)

        if looks_like_idx_ticker(value):
            return clean_ticker(value)

    return None


def extract_score(row):
    if not isinstance(row, dict):
        return 50.0

    score_keys = [
        "score",
        "confidence",
        "rank_score",
        "total_score",
        "signal_score",
        "opportunity_score",
        "alpha_score",
        "strength",
        "probability",
    ]

    for key in score_keys:
        value = safe_float(
            row.get(key)
        )

        if value is None:
            continue

        if (
            key == "probability"
            and 0 <= value <= 1
        ):
            value *= 100

        return value

    rank = safe_float(
        row.get("rank")
    )

    if rank is not None and rank > 0:
        return max(
            0,
            101 - rank,
        )

    return 50.0


def row_has_market_context(row):
    if not isinstance(row, dict):
        return False

    useful_keys = {
        "price",
        "close",
        "last_price",
        "current_price",
        "entry",
        "entry_price",
        "entry_low",
        "entry_high",
        "entry_zone_low",
        "entry_zone_high",
        "breakout_price",
        "confirmation_price",
        "trigger_price",
        "stop",
        "stop_loss",
        "invalidation_price",
        "target",
        "target_1",
        "target_2",
        "score",
        "confidence",
        "rank",
        "signal",
        "recommendation",
        "action",
        "reason",
        "thesis",
        "volume",
        "momentum",
        "rsi",
    }

    return bool(
        useful_keys.intersection(
            row.keys()
        )
    )


# ============================================================
# RECURSIVE DISCOVERY
# ============================================================

def collect_candidate_rows(
    node,
    output,
    path="root",
    inherited_ticker=None,
):
    """
    Supports BOTH:

    1. ticker stored as a field:
       {"ticker": "BBRI", "score": 80}

    2. ticker stored as dictionary key:
       {
           "BBRI": {
               "score": 80,
               "price": 4500
           }
       }

    and arbitrary nesting under markets/BEI/etc.
    """

    if isinstance(node, dict):

        own_ticker = extract_ticker_from_row(
            node
        )

        ticker = (
            own_ticker
            or inherited_ticker
        )

        if (
            ticker
            and looks_like_idx_ticker(ticker)
            and row_has_market_context(node)
        ):
            output.append(
                {
                    "ticker": clean_ticker(
                        ticker
                    ),
                    "raw": node,
                    "path": path,
                }
            )

        for key, value in node.items():

            key_ticker = None

            if looks_like_idx_ticker(key):
                key_ticker = clean_ticker(
                    key
                )

            next_ticker = (
                key_ticker
                or ticker
            )

            collect_candidate_rows(
                value,
                output,
                path=f"{path}.{key}",
                inherited_ticker=next_ticker,
            )

    elif isinstance(node, list):

        for index, value in enumerate(
            node
        ):
            collect_candidate_rows(
                value,
                output,
                path=f"{path}[{index}]",
                inherited_ticker=(
                    inherited_ticker
                ),
            )


def extract_candidates(scan):
    discovered = []

    collect_candidate_rows(
        scan,
        discovered,
    )

    print(
        f"Raw stock-like objects found: "
        f"{len(discovered)}",
        flush=True,
    )

    best_by_ticker = {}

    for item in discovered:

        ticker = item["ticker"]
        row = item["raw"]

        score = extract_score(
            row
        )

        candidate = {
            "ticker": ticker,
            "score": score,
            "raw": row,
            "path": item["path"],
        }

        existing = best_by_ticker.get(
            ticker
        )

        if (
            existing is None
            or score > existing["score"]
        ):
            best_by_ticker[
                ticker
            ] = candidate

    candidates = list(
        best_by_ticker.values()
    )

    candidates.sort(
        key=lambda item: item["score"],
        reverse=True,
    )

    return candidates[
        :MAX_CANDIDATES
    ]


# ============================================================
# VALUE EXTRACTION
# ============================================================

def first_number(row, keys):
    if not isinstance(row, dict):
        return None

    for key in keys:
        value = safe_float(
            row.get(key)
        )

        if value is not None:
            return value

    return None


def first_text(row, keys):
    if not isinstance(row, dict):
        return None

    for key in keys:
        value = row.get(key)

        if value is None:
            continue

        if isinstance(
            value,
            (str, int, float),
        ):
            text = str(
                value
            ).strip()

            if text:
                return text

    return None


# ============================================================
# BUILD WATCHLIST ROW
# ============================================================

def build_watchlist_row(candidate):
    row = candidate["raw"]

    ticker = candidate["ticker"]

    current_price = first_number(
        row,
        [
            "price",
            "last_price",
            "current_price",
            "close",
        ],
    )

    confirmation_price = first_number(
        row,
        [
            "confirmation_price",
            "breakout_price",
            "trigger_price",
            "entry_trigger",
            "buy_above",
            "entry_price",
        ],
    )

    # If slow engine has no explicit trigger,
    # use current reference price.
    # Fast Engine STILL requires its own
    # 1m + 5m confirmation before BUY.
    if confirmation_price is None:
        confirmation_price = (
            current_price
        )

    invalidation_price = first_number(
        row,
        [
            "invalidation_price",
            "stop_loss",
            "stop",
            "risk_price",
        ],
    )

    entry_low = first_number(
        row,
        [
            "entry_zone_low",
            "entry_low",
            "buy_zone_low",
        ],
    )

    entry_high = first_number(
        row,
        [
            "entry_zone_high",
            "entry_high",
            "buy_zone_high",
        ],
    )

    reason = first_text(
        row,
        [
            "reason",
            "thesis",
            "signal",
            "recommendation",
            "action",
            "setup",
        ],
    )

    if not reason:
        reason = (
            "Auto-selected by "
            "HANZ slow engine"
        )

    priority = int(
        max(
            0,
            min(
                100,
                round(
                    candidate["score"]
                ),
            ),
        )
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
        "reason": reason,
        "updated_at": now_iso(),
    }


# ============================================================
# SUPABASE UPSERT
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
# DEBUG STRUCTURE
# ============================================================

def print_scan_structure(scan):
    print(
        "SCAN ROOT TYPE:",
        type(scan).__name__,
        flush=True,
    )

    if not isinstance(scan, dict):
        return

    print(
        "SCAN TOP LEVEL KEYS:",
        list(scan.keys()),
        flush=True,
    )

    markets = scan.get(
        "markets"
    )

    print(
        "MARKETS TYPE:",
        type(markets).__name__,
        flush=True,
    )

    if isinstance(markets, dict):

        print(
            "MARKETS KEYS:",
            list(markets.keys()),
            flush=True,
        )

        for market_name, value in (
            markets.items()
        ):

            print(
                f"MARKET "
                f"{market_name} TYPE: "
                f"{type(value).__name__}",
                flush=True,
            )

            if isinstance(
                value,
                dict,
            ):
                print(
                    f"MARKET "
                    f"{market_name} KEYS: "
                    f"{list(value.keys())[:20]}",
                    flush=True,
                )

            elif isinstance(
                value,
                list,
            ):
                print(
                    f"MARKET "
                    f"{market_name} ITEMS: "
                    f"{len(value)}",
                    flush=True,
                )


# ============================================================
# MAIN
# ============================================================

def main():
    print(
        "HANZ Auto Watchlist "
        "Feeder v3 started.",
        flush=True,
    )

    scan = load_scan()

    print_scan_structure(
        scan
    )

    candidates = (
        extract_candidates(
            scan
        )
    )

    print(
        f"Auto-watchlist "
        f"candidates found: "
        f"{len(candidates)}",
        flush=True,
    )

    if not candidates:

        print(
            "No valid candidates "
            "discovered inside "
            "paper scan JSON.",
            flush=True,
        )

        return

    rows = []

    for candidate in candidates:

        row = build_watchlist_row(
            candidate
        )

        rows.append(row)

        print(
            f"Candidate: "
            f"{row['ticker']} | "
            f"score="
            f"{candidate['score']:.1f} | "
            f"priority="
            f"{row['priority']} | "
            f"confirmation="
            f"{row['confirmation_price']} | "
            f"path="
            f"{candidate['path']}",
            flush=True,
        )

    upsert_watchlist(
        rows
    )

    print(
        "HANZ Auto Watchlist "
        "Feeder completed.",
        flush=True,
    )


if __name__ == "__main__":
    main()
