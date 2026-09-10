"""Runtime entry point for HANZ single momentum-entry scoring + early trigger."""

from . import swing_trading_engine as engine
from .momentum_entry_score import momentum_entry_score
from .early_momentum_trigger import install as install_early_momentum_trigger


# Keep CRV3 prefix for dashboard backwards compatibility.
SCORE_VERSION = "CRV3_MES2_2026_09_10_EARLY_MOMENTUM_ENTRY"


def main():
    # One visible score: momentum-entry score.
    engine.canonical_rank_score = momentum_entry_score
    engine.CANONICAL_RANK_VERSION = SCORE_VERSION

    # Earlier measured confirmation: minor pivot break + volume + structure,
    # while keeping the existing risk/portfolio/alert safeguards intact.
    install_early_momentum_trigger(engine)

    engine.main()


if __name__ == "__main__":
    main()
