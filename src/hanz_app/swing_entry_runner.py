"""Runtime entry point for HANZ momentum scoring, early trigger and auto decision."""

from . import swing_trading_engine as engine
from .momentum_entry_score import momentum_entry_score
from .early_momentum_trigger import install as install_early_momentum_trigger
from .market_data_router import install as install_market_data_router
from .support_bounce_intelligence import install as install_support_bounce_intelligence


# Keep CRV3 prefix for dashboard backwards compatibility.
SCORE_VERSION = "CRV3_MES7_GRADUATED_OPPORTUNITY_2026_09_14"


def graduated_top5_score(result, risk_validation):
    """Balanced Top-5 ranking: soft brake, not full stop.

    HANZ should rank the best *available* opportunities, not demand perfection.

    Hard-excluded from Opportunity Top 5:
      - AVOID: fundamentally/tactically unsuitable for a fresh entry.
      - hard data/structure blocks already return score 0 inside MES.

    Still rankable, with natural score caps/penalties from MES:
      - BUY: highest priority when quality is genuinely confirmed.
      - WAIT_TRIGGER: fresh bounce / early setup awaiting final confirmation.
      - WAIT: developing setup; may appear below stronger candidates.
      - RESISTANCE_WAIT: may remain visible only at a low score so it cannot
        dominate a cleaner support-bounce candidate.
      - DO_NOT_CHASE / TP_RISK: kept out of the opportunity list because these
        are management/warning states, not fresh-entry opportunities.

    This prevents the previous binary behaviour where one strict rule emptied
    the whole radar.
    """
    rv = risk_validation or {}
    score = int(momentum_entry_score(result, rv) or 0)
    action = str(rv.get("hanz_action") or "").upper()

    hard_excluded = action in {"AVOID", "DO_NOT_CHASE", "TP_RISK"}
    if hard_excluded:
        rv["top5_excluded"] = True
        rv["top5_exclusion_reason"] = (
            f"HANZ action {action or 'UNKNOWN'} is not a fresh-entry opportunity"
        )
        return 0

    # Preserve graded opportunity scores. Resistance is a brake, not a wall:
    # the scoring model already caps RESISTANCE_WAIT <=39, so it can only appear
    # when the market offers very few better setups.
    rv["top5_excluded"] = False
    rv["top5_exclusion_reason"] = None
    rv["top5_priority_class"] = {
        "BUY": "A_CONFIRMED",
        "WAIT_TRIGGER": "B_EARLY",
        "WAIT": "C_DEVELOPING",
        "RESISTANCE_WAIT": "D_RESISTANCE",
    }.get(action, "C_DEVELOPING")
    return score


def main():
    install_market_data_router(engine)
    install_support_bounce_intelligence(engine)
    engine.canonical_rank_score = graduated_top5_score
    engine.CANONICAL_RANK_VERSION = SCORE_VERSION
    install_early_momentum_trigger(engine)
    engine.main()


if __name__ == "__main__":
    main()
