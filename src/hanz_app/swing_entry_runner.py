"""Runtime entry point for HANZ momentum scoring, early trigger and auto decision."""

from . import swing_trading_engine as engine
from .momentum_entry_score import momentum_entry_score
from .early_momentum_trigger import install as install_early_momentum_trigger
from .market_data_router import install as install_market_data_router
from .support_bounce_intelligence import install as install_support_bounce_intelligence
from .foreign_entry_intelligence import install as install_foreign_entry_intelligence
from .risk_context_quality import install as install_risk_context_quality
from .data_quality_v12 import install as install_data_quality_v12


# Keep CRV3 prefix for dashboard backwards compatibility.
SCORE_VERSION = "CRV3_MES8_RELATIVE100_FOREIGN_CONTEXT_V12_2026_10_12"


def _num(value, default=0.0):
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def graduated_top5_score(result, risk_validation):
    """Relative opportunity ranking for the 100-stock screener universe.

    Doctrine:
      * Rank the BEST AVAILABLE opportunities first, not only perfect setups.
      * AVOID is never an opportunity candidate. In a 100-name screener it
        belongs to the bottom-decile / tail of the ranking (conceptually ranks
        ~90-100), never Top 5.
      * BUY / WAIT_TRIGGER / WAIT / RESISTANCE_WAIT remain rankable with graded
        scores so the radar does not go empty just because nothing is perfect.
      * DO_NOT_CHASE / TP_RISK are warning/management states and do not belong in
        the fresh-entry Top 5.
      * Foreign flow is a bounded confirmation/ranking input. It can move a
        technically valid candidate up or down, but it never creates BUY by
        itself and never bypasses action/risk exclusions.
      * V12 context quality adds bounded market-breadth and sector-quality
        adjustments; context cannot manufacture a BUY or bypass hard gates.

    The full screener can still display AVOID rows for transparency, but the
    opportunity radar must not promote them.
    """
    rv = risk_validation or {}
    technical_score = int(momentum_entry_score(result, rv) or 0)
    action = str(rv.get("hanz_action") or "").upper()

    foreign_score = _num(rv.get("foreign_flow_score"), 0.0)
    foreign_adjustment = int(max(-12, min(12, round(foreign_score))))
    rv["technical_score_before_foreign"] = technical_score
    rv["foreign_rank_adjustment"] = foreign_adjustment
    rv["foreign_rank_policy"] = "CONFIRMATION_ONLY_BOUNDED_12"

    market_breadth = _num(rv.get("market_breadth_score"), None)
    sector_score = _num(rv.get("sector_score"), None)
    context_adjustment = 0

    if market_breadth is not None:
        if market_breadth >= 70:
            context_adjustment += 4
        elif market_breadth >= 55:
            context_adjustment += 2
        elif market_breadth < 30:
            context_adjustment -= 7
        elif market_breadth < 40:
            context_adjustment -= 4

    if sector_score is not None:
        if sector_score >= 70:
            context_adjustment += 5
        elif sector_score >= 60:
            context_adjustment += 3
        elif sector_score < 20:
            context_adjustment -= 12
        elif sector_score < 40:
            context_adjustment -= 7

    context_adjustment = int(max(-15, min(8, context_adjustment)))
    rv["context_rank_adjustment"] = context_adjustment
    rv["context_rank_policy"] = "MARKET_BREADTH_PLUS_SECTOR_BOUNDED"

    data_confidence = _num(rv.get("data_confidence_score"), None)
    data_adjustment = 0
    if data_confidence is not None:
        if data_confidence >= 95:
            data_adjustment = 2
        elif data_confidence < 50:
            data_adjustment = -8
        elif data_confidence < 70:
            data_adjustment = -4
    rv["data_rank_adjustment"] = data_adjustment

    raw_score = max(
        0,
        min(100, technical_score + foreign_adjustment + context_adjustment + data_adjustment),
    )

    if action == "AVOID":
        tail_score = max(0, min(9, round(raw_score * 9 / 49))) if raw_score > 0 else 0
        rv["top5_excluded"] = True
        rv["top5_exclusion_reason"] = "AVOID belongs to the bottom-decile, not Opportunity Top 5"
        rv["ranking_bucket"] = "Z_BOTTOM_10_AVOID"
        rv["relative_rank_policy"] = "BOTTOM_DECILE_90_100"
        rv["canonical_raw_score_before_bucket"] = raw_score
        return tail_score

    if action == "DO_NOT_CHASE":
        rv["top5_excluded"] = True
        rv["top5_exclusion_reason"] = "HANZ action DO_NOT_CHASE is not a fresh-entry opportunity"
        rv["ranking_bucket"] = "Y_WARNING"
        rv["canonical_raw_score_before_bucket"] = raw_score
        return max(10, min(24, raw_score))

    if action == "TP_RISK":
        rv["top5_excluded"] = False
        rv["top5_exclusion_reason"] = None
        rv["top5_priority_class"] = "D_CAUTION"
        rv["ranking_bucket"] = "D_CAUTION_TP_RISK"
        rv["relative_rank_policy"] = "BEST_AVAILABLE_CAUTION"
        rv["canonical_raw_score_before_bucket"] = raw_score
        return max(10, min(24, raw_score))

    floors = {
        "BUY": 70,
        "WAIT_TRIGGER": 55,
        "WAIT": 35,
        "RESISTANCE_WAIT": 20,
    }
    priority = {
        "BUY": "A_CONFIRMED",
        "WAIT_TRIGGER": "B_EARLY",
        "WAIT": "C_DEVELOPING",
        "RESISTANCE_WAIT": "D_RESISTANCE",
    }

    rv["top5_excluded"] = False
    rv["top5_exclusion_reason"] = None
    rv["top5_priority_class"] = priority.get(action, "C_DEVELOPING")
    rv["ranking_bucket"] = priority.get(action, "C_DEVELOPING")
    rv["relative_rank_policy"] = "BEST_AVAILABLE_FIRST"

    score = max(floors.get(action, 25), raw_score)
    return min(100, score)


def actionable_top5_score(result, risk_validation):
    """Compatibility gate for the strict fresh-entry Top-5 contract."""
    rv = risk_validation or {}
    score = graduated_top5_score(result, rv)
    action = str(rv.get("hanz_action") or "").upper()
    if action in {"AVOID", "DO_NOT_CHASE", "TP_RISK", "RESISTANCE_WAIT"}:
        rv["top5_excluded"] = True
        if not rv.get("top5_exclusion_reason"):
            rv["top5_exclusion_reason"] = f"HANZ action {action} is not a fresh-entry Top 5 candidate"
        return 0
    return score


def main():
    install_market_data_router(engine)
    install_support_bounce_intelligence(engine)
    install_foreign_entry_intelligence(engine)
    install_risk_context_quality(engine)
    install_data_quality_v12(engine)
    engine.canonical_rank_score = graduated_top5_score
    engine.CANONICAL_RANK_VERSION = SCORE_VERSION
    install_early_momentum_trigger(engine)
    engine.main()


if __name__ == "__main__":
    main()
