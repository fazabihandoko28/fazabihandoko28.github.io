"""One-shot completed-bar refresh using the HANZ Momentum Entry Score.

This module exists only to refresh the monitor table immediately after the
single-score model is deployed, without waiting for the scheduled post-close
scanner. It uses maintenance_mode=True, so it cannot create a new actionable
BUY, alert, push, or portfolio action.
"""

import json

from . import swing_trading_engine as engine
from .momentum_entry_score import momentum_entry_score


SCORE_VERSION = "CRV3_MES1_2026_09_10_MOMENTUM_ENTRY"


def main():
    engine.canonical_rank_score = momentum_entry_score
    engine.CANONICAL_RANK_VERSION = SCORE_VERSION
    engine._REAL_MONEY_CONTEXT = engine.build_real_money_context()

    universe = engine.fetch_universe()
    counts = {"UPDATED": 0, "ERROR": 0}

    print(
        f"HANZ MOMENTUM ENTRY ONE-SHOT REFRESH | universe={len(universe)} | "
        "maintenance_mode=TRUE | new BUY/alert/push=BLOCKED",
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
