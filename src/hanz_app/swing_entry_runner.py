"""Runtime entry point for HANZ momentum scoring, early trigger and auto decision."""

from . import swing_trading_engine as engine
from .momentum_entry_score import momentum_entry_score
from .early_momentum_trigger import install as install_early_momentum_trigger
from .market_data_router import install as install_market_data_router
from .support_bounce_intelligence import install as install_support_bounce_intelligence


# Keep CRV3 prefix for dashboard backwards compatibility.
SCORE_VERSION = "CRV3_MES6_FRESH_BOUNCE_FIRST_2026_09_14"


def actionable_top5_score(result, risk_validation):
    """Return canonical score only for genuinely actionable fresh-entry names.

    The dashboard eligibility rule already rejects canonical score <= 0.  By
    applying this backend hard gate, old frontend logic can no longer put AVOID,
    DO_NOT_CHASE, TP_RISK, RESISTANCE_WAIT, or generic WAIT names into Big Rank.

    Allowed:
      - BUY: fully confirmed fresh entry.
      - WAIT_TRIGGER: fresh support bounce confirmed, but final trigger/volume/R:R
        confirmation is still pending.
    """
    score = momentum_entry_score(result, risk_validation)
    action = str((risk_validation or {}).get("hanz_action") or "").upper()
    if action not in {"BUY", "WAIT_TRIGGER"}:
        (risk_validation or {})["top5_excluded"] = True
        (risk_validation or {})["top5_exclusion_reason"] = (
            f"HANZ action {action or 'UNKNOWN'} is not actionable for fresh-entry Top 5"
        )
        return 0

    (risk_validation or {})["top5_excluded"] = False
    (risk_validation or {})["top5_exclusion_reason"] = None
    return score


def main():
    install_market_data_router(engine)
    install_support_bounce_intelligence(engine)
    engine.canonical_rank_score = actionable_top5_score
    engine.CANONICAL_RANK_VERSION = SCORE_VERSION
    install_early_momentum_trigger(engine)
    engine.main()


if __name__ == "__main__":
    main()
