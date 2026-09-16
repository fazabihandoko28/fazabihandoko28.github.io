"""HANZ foreign-flow entry integration.

Foreign activity is a confirmation/ranking input, never a standalone BUY trigger.
The core engine already stores/query foreign flow for portfolio exits; this
adapter wires the same evidence into fresh-entry risk validation and provides an
absolute-IDR fallback for data sources that publish net foreign value without a
per-ticker total traded value (for example a midday foreign-activity table).
"""

from __future__ import annotations


def _num(value, default=None):
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _absolute_flow_classification(net_1d):
    """Return (status, score, reason) from absolute 1D net foreign value in IDR.

    The score is deliberately bounded. It can reorder otherwise valid
    opportunities, but cannot by itself create a BUY signal.
    """
    value = _num(net_1d)
    if value is None:
        return None

    if value >= 40_000_000_000:
        return ("ACCUMULATING", 12, "Strong 1D foreign accumulation by net value.")
    if value >= 15_000_000_000:
        return ("ACCUMULATING", 9, "1D foreign accumulation by net value.")
    if value >= 5_000_000_000:
        return ("MILD_ACCUMULATION", 5, "Moderate 1D foreign net buy.")
    if value >= 1_000_000_000:
        return ("MILD_ACCUMULATION", 2, "Positive 1D foreign net buy.")

    if value <= -100_000_000_000:
        return ("DISTRIBUTING", -12, "Heavy 1D foreign distribution by net value.")
    if value <= -40_000_000_000:
        return ("DISTRIBUTING", -9, "Strong 1D foreign distribution by net value.")
    if value <= -15_000_000_000:
        return ("DISTRIBUTION_WATCH", -7, "1D foreign distribution watch.")
    if value <= -5_000_000_000:
        return ("CAUTION", -4, "1D foreign net sell caution.")
    if value <= -1_000_000_000:
        return ("CAUTION", -2, "Negative 1D foreign net sell.")

    return ("NEUTRAL", 0, "1D foreign flow is too small to affect ranking.")


def install(engine):
    """Patch the swing engine so foreign flow participates in entry ranking."""
    if getattr(engine, "_foreign_entry_intelligence_installed", False):
        return engine

    base_snapshot = engine.foreign_flow_snapshot
    base_validation = engine.real_money_validation

    def foreign_flow_snapshot(ticker):
        out = dict(base_snapshot(ticker) or {})

        # Existing percentage-based multi-day logic remains preferred whenever
        # total_value is available. If the source only supplies net IDR value,
        # fall back to a conservative absolute-value classification.
        pct_available = any(
            out.get(key) is not None
            for key in ("net_pct_1d", "net_pct_3d", "net_pct_5d")
        )
        if out.get("available") and not pct_available:
            fallback = _absolute_flow_classification(out.get("net_1d"))
            if fallback is not None:
                status, score, reason = fallback
                out["status"] = status
                out["score"] = score
                out["reason"] = reason
                out["scoring_basis"] = "ABSOLUTE_NET_IDR_1D"
        else:
            out["scoring_basis"] = "PCT_MULTI_DAY" if pct_available else "UNKNOWN"
        return out

    def real_money_validation(ticker, daily, result, levels, fundamental, context):
        rv = base_validation(ticker, daily, result, levels, fundamental, context)
        foreign = foreign_flow_snapshot(ticker)
        rv = engine.apply_foreign_flow_to_risk_validation(rv, foreign)
        rv["foreign_flow_available"] = bool(foreign.get("available"))
        rv["foreign_flow_scoring_basis"] = foreign.get("scoring_basis")
        return rv

    engine.foreign_flow_snapshot = foreign_flow_snapshot
    engine.real_money_validation = real_money_validation
    engine._foreign_entry_intelligence_installed = True
    return engine
