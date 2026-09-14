"""Runtime entry point for HANZ momentum scoring, early trigger and auto decision."""

from . import swing_trading_engine as engine
from .momentum_entry_score import momentum_entry_score
from .early_momentum_trigger import install as install_early_momentum_trigger
from .market_data_router import install as install_market_data_router
from .support_bounce_intelligence import install as install_support_bounce_intelligence


# Keep CRV3 prefix for dashboard backwards compatibility.
SCORE_VERSION = "CRV3_MES5_BOUNCE_2026_09_14_INTRADAY"


def main():
    install_market_data_router(engine)
    install_support_bounce_intelligence(engine)
    engine.canonical_rank_score = momentum_entry_score
    engine.CANONICAL_RANK_VERSION = SCORE_VERSION
    install_early_momentum_trigger(engine)
    engine.main()


if __name__ == "__main__":
    main()
