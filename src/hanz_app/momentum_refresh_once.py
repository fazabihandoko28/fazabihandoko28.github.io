"""One-shot completed-bar refresh using HANZ Momentum Entry Score + early trigger."""

import json

from . import swing_trading_engine as engine
from .momentum_entry_score import momentum_entry_score
from .early_momentum_trigger import install as install_early_momentum_trigger


SCORE_VERSION = "CRV3_MES2_2026_09_10_EARLY_MOMENTUM_ENTRY"


def main():
    engine.canonical_rank_score = momentum_entry_score
    engine.CANONICAL_RANK_VERSION = SCORE_VERSION
    install_early_momentum_trigger(engine)
    engine._REAL_MONEY_CONTEXT = engine.build_real_money_context()

    universe = engine.fetch_universe()
    counts = {"UPDATED": 0, "ERROR": 0}

    print(
        f"HANZ MOMENTUM ENTRY ONE-SHOT REFRESH | universe={len(universe)} | "
        "early-trigger=V2 | maintenance_mode=TRUE | new BUY/alert/push=BLOCKED",
        flush=True,
    )

    for ticker in universe:
        try:
            engine.scan_symbol(ticker, maintenance_mode=True)
            counts["UPDATED"] += 1
        except Exception as exc:
            counts["ERROR"] += 1
            print(f"MOMENTUM REFRESH {ticker} failed: {exc}", flush=True)

    print("HANZ MOMENTUM ENTRY ONE-SHOT REFRESH complete: " + json.dumps(counts), flush=True)


if __name__ == "__main__":
    main()
