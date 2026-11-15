"""G2 research adapter for real monitor snapshots; no execution permissions.

Monitor records must include updated_at and risk_validation. Historical
snapshots are selected at a declared cutoff, without using OOS outcomes.
"""
from __future__ import annotations

from datetime import datetime, timezone

from hanz_app.research.g2_candidate_replacement import select_top_five


def _monitor_day(value):
    if not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            return None
        return dt.astimezone(timezone.utc).date().isoformat()
    except ValueError:
        return None


def select_monitor_top_five(monitor_rows, *, as_of):
    """Adapt actual monitor field names to fail-closed G2 research selection."""
    # Reuse existing research eligibility checks; this does NOT grant BUY.
    from hanz_app.research.generate_top5_5y_backtest import _eligible, _rank

    adapted = []
    for row in monitor_rows:
        if not isinstance(row, dict):
            continue
        day = _monitor_day(row.get("updated_at"))
        if day is None:
            continue
        adapted.append({
            "ticker": row.get("ticker"),
            "snapshot_date": day,
            "eligible": bool(_eligible(row)),
            "rank_score": _rank(row),
        })
    result = select_top_five(adapted, as_of=as_of)
    result["source"] = "hanz_swing_signal_monitor"
    result["source_rows"] = len(adapted)
    result["live_verified"] = False
    return result
