"""G2 research adapter for real monitor snapshots; no execution permissions.

Monitor records must include updated_at and risk_validation. Historical
snapshots are selected at a declared cutoff, without using OOS outcomes.
"""
from __future__ import annotations

from datetime import datetime, timezone, time, date

from hanz_app.research.g2_candidate_replacement import select_top_five


def _parse_timestamp(value):
    if not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        return None
    return dt.astimezone(timezone.utc)


def _cutoff(as_of):
    if not isinstance(as_of, str):
        raise ValueError("Explicit UTC cutoff required")
    try:
        if len(as_of) == 10:
            day = date.fromisoformat(as_of)
            if day.isoformat() != as_of:
                raise ValueError("Invalid date")
            return datetime.combine(day, time.max, tzinfo=timezone.utc), day.isoformat()
        dt = _parse_timestamp(as_of)
        if dt is None:
            raise ValueError("Timezone-aware UTC cutoff required")
        return dt, dt.date().isoformat()
    except (ValueError, OverflowError) as exc:
        raise ValueError("Invalid UTC cutoff") from exc


def select_monitor_top_five(monitor_rows, *, as_of):
    """Adapt actual monitor field names to fail-closed G2 research selection."""
    # Reuse existing research eligibility checks; this does NOT grant BUY.
    from hanz_app.research.generate_top5_5y_backtest import _eligible, _rank

    cutoff, cutoff_day = _cutoff(as_of)
    adapted = []
    # Exclude future records before ranking and ticker deduplication.
    valid = []
    for row in monitor_rows:
        if not isinstance(row, dict):
            continue
        timestamp = _parse_timestamp(row.get("updated_at"))
        if timestamp is not None and timestamp <= cutoff:
            valid.append((timestamp, row))
    # A contradictory newest snapshot cannot be resolved by input ordering.
    # Fail closed for that ticker rather than selecting an arbitrary record.
    latest = {}
    conflicts = set()
    for timestamp, row in sorted(valid, key=lambda pair: pair[0], reverse=True):
        ticker = str(row.get("ticker") or "").strip().upper()
        signature = (bool(_eligible(row)), _rank(row))
        if ticker in latest:
            if timestamp == latest[ticker][0] and signature != latest[ticker][1]:
                conflicts.add(ticker)
            continue
        latest[ticker] = (timestamp, signature, row)
    for ticker, (timestamp, signature, row) in latest.items():
        if ticker in conflicts:
            continue
        adapted.append({
            "ticker": row.get("ticker"),
            "snapshot_date": timestamp.date().isoformat(),
            "eligible": bool(_eligible(row)),
            "rank_score": _rank(row),
        })
    result = select_top_five(adapted, as_of=cutoff_day)
    result["source"] = "hanz_swing_signal_monitor"
    result["source_rows"] = len(adapted)
    result["live_verified"] = False
    return result
