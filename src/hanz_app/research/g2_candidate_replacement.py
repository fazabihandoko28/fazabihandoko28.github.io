"""G2 research-only deterministic candidate replacement; never authorizes BUY."""
from __future__ import annotations

import math
import re
from datetime import date
from collections.abc import Iterable, Mapping


def _parse_date(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def select_top_five(rows: Iterable[Mapping], *, as_of: str, limit: int = 5) -> dict:
    """Select explicitly eligible snapshots supplied newest-first at cutoff.

    OOS results must not be used as ranking inputs. Never force-fill slots.
    """
    if _parse_date(as_of) is None:
        raise ValueError("Explicit YYYY-MM-DD selection cutoff required")
    if limit != 5:
        raise ValueError("G2 research Top 5 selection requires exactly five slots")
    latest = {}
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        symbol = str(row.get("ticker") or "").strip().upper()
        if not re.fullmatch(r"[A-Z0-9]{1,12}", symbol):
            continue
        stamp = row.get("snapshot_date")
        parsed = _parse_date(stamp)
        if parsed is None or parsed > _parse_date(as_of):
            continue
        if symbol not in latest or parsed > latest[symbol][0]:
            latest[symbol] = (parsed, row)
    eligible = []
    excluded = {}
    for symbol, (_, row) in latest.items():
        score = row.get("rank_score")
        if (row.get("eligible") is not True or isinstance(score, bool)
                or not isinstance(score, (int, float)) or not math.isfinite(score)
                or not 0 <= score <= 100):
            excluded[symbol] = "NOT_ELIGIBLE_OR_INVALID_SCORE"
            continue
        eligible.append((symbol, score))
    eligible.sort(key=lambda item: (-item[1], item[0]))
    selected = [symbol for symbol, _ in eligible[:limit]]
    return {
        "as_of": as_of,
        "selected": selected,
        "vacant_slots": limit - len(selected),
        "selection_complete": len(selected) == limit,
        "excluded": excluded,
        "research_only": True,
        "oos_certified": False,
        "buy_authorized": False,
    }
