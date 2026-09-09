"""Runtime entry point that installs the HANZ single momentum-entry scorer."""

from . import swing_trading_engine as engine
from .momentum_entry_score import momentum_entry_score


SCORE_VERSION = "MES1_2026_09_09_SINGLE_ENTRY_SCORE"


def main():
    # Replace only the canonical dashboard/ranking score.
    # Technical state, risk gates, alerts, sizing, and portfolio logic remain intact.
    engine.canonical_rank_score = momentum_entry_score
    engine.CANONICAL_RANK_VERSION = SCORE_VERSION
    engine.main()


if __name__ == "__main__":
    main()
