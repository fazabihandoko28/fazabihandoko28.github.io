"""Runtime entry point for HANZ momentum scoring, early trigger and auto decision."""

from . import swing_trading_engine as engine
from .momentum_entry_score import momentum_entry_score
from .early_momentum_trigger import install as install_early_momentum_trigger
from .market_data_router import install as install_market_data_router
from .support_bounce_intelligence import install as install_support_bounce_intelligence


# Keep CRV3 prefix for dashboard backwards compatibility.
SCORE_VERSION = "CRV3_MES8_RELATIVE100_BOTTOM_DECILE_2026_09_14"


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

    The full screener can still display AVOID rows for transparency, but the
    opportunity radar must not promote them.
    """
    rv = risk_validation or {}
    raw_score = int(momentum_entry_score(result, rv) or 0)
    action = str(rv.get("hanz_action") or "").upper()

    # Absolute ranking doctrine for AVOID: bottom-decile only.
    # Keep a tiny 0-9 tail score so full-universe sorting can still order AVOID
    # names among themselves while guaranteeing they cannot compete with normal
    # opportunity candidates.
    if action == "AVOID":
        tail_score = max(0, min(9, round(raw_score * 9 / 49))) if raw_score > 0 else 0
        rv["top5_excluded"] = True
        rv["top5_exclusion_reason"] = "AVOID belongs to the bottom-decile, not Opportunity Top 5"
        rv["ranking_bucket"] = "Z_BOTTOM_10_AVOID"
        rv["relative_rank_policy"] = "BOTTOM_DECILE_90_100"
        rv["canonical_raw_score_before_bucket"] = raw_score
        return tail_score

    # These are not fresh-entry opportunities either. Keep them above AVOID in
    # the full screener, but out of Opportunity Top 5.
    if action in {"DO_NOT_CHASE", "TP_RISK"}:
        rv["top5_excluded"] = True
        rv["top5_exclusion_reason"] = f"HANZ action {action} is a warning/management state"
        rv["ranking_bucket"] = "Y_WARNING"
        rv["canonical_raw_score_before_bucket"] = raw_score
        return max(10, min(24, raw_score))

    # Rankable opportunity states. Their natural MES score remains the main
    # differentiator; these floors only preserve category ordering when the raw
    # score is unusually weak.
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


def main():
    install_market_data_router(engine)
    install_support_bounce_intelligence(engine)
    engine.canonical_rank_score = graduated_top5_score
    engine.CANONICAL_RANK_VERSION = SCORE_VERSION
    install_early_momentum_trigger(engine)
    engine.main()


if __name__ == "__main__":
    main()
