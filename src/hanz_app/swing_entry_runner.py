"""Runtime entry point for HANZ momentum scoring, early trigger and auto decision."""

from . import swing_trading_engine as engine
from .momentum_entry_score import momentum_entry_score
from .early_momentum_trigger import install as install_early_momentum_trigger
from .market_data_router import install as install_market_data_router


# Keep CRV3 prefix for dashboard backwards compatibility.
SCORE_VERSION = "CRV3_MES4_2026_09_11_DATA_QUALITY_GATE"


def main():
    # Route daily data first so every downstream calculation uses the selected
    # primary feed and receives independent IDX verification when configured.
    install_market_data_router(engine)

    # One visible score: momentum-entry score.
    engine.canonical_rank_score = momentum_entry_score
    engine.CANONICAL_RANK_VERSION = SCORE_VERSION

    # Earlier measured confirmation: minor pivot break + volume + structure,
    # while keeping the existing risk/portfolio/alert safeguards intact.
    install_early_momentum_trigger(engine)

    engine.main()


if __name__ == "__main__":
    main()
