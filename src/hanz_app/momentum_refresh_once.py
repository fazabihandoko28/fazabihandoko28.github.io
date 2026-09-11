"""One-shot completed-bar refresh using HANZ Momentum Entry Score + auto decision."""

import json

from . import swing_trading_engine as engine
from .momentum_entry_score import momentum_entry_score
from .early_momentum_trigger import install as install_early_momentum_trigger
from .market_data_router import install as install_market_data_router


SCORE_VERSION = "CRV3_MES5_2026_09_11_STRICT_TIMING"


def main():
    install_market_data_router(engine)
    engine.canonical_rank_score = momentum_entry_score
    engine.CANONICAL_RANK_VERSION = SCORE_VERSION
    install_early_momentum_trigger(engine)
    engine._REAL_MONEY_CONTEXT = engine.build_real_money_context()

    universe = engine.fetch_universe()
    counts = {"UPDATED": 0, "ERROR": 0}

    print(
        f"HANZ MOMENTUM ENTRY ONE-SHOT REFRESH | universe={len(universe)} | "
        "auto-decision=MES5_STRICT_TIMING | data-quality-gate=ON | maintenance_mode=TRUE | broker execution=BLOCKED",
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
