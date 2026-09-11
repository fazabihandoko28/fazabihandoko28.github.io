import json

from .swing_trading_engine import (
    idx_market_session,
    jakarta_now,
    previous_idx_trading_day,
    next_idx_trading_day,
    monitor_swing_portfolio,
)
from .portfolio_exit_guard import monitor_early_exit_warnings


def run_portfolio_cycle():
    market = idx_market_session()
    now_wib = jakarta_now()

    previous_day = previous_idx_trading_day(
        now_wib.date()
    )
    next_day = next_idx_trading_day(
        now_wib.date()
    )

    print(
        "HANZ SWING PORTFOLIO MONITOR START | "
        f"IDX={market['state']} | "
        f"reason={market['reason']} | "
        f"WIB={now_wib.strftime('%Y-%m-%d %H:%M')} | "
        f"previous={previous_day} | "
        f"next={next_day}",
        flush=True,
    )

    if not market["is_trading_day"]:
        print(
            "PORTFOLIO MONITOR skipped: IDX is not a trading day. "
            "No price trigger, alert or push.",
            flush=True,
        )
        return

    # Run only while regular market is actually trading.
    # Lunch break is skipped; POST_CLOSE is handled by the scanner workflow.
    if market["state"] not in {
        "SESSION_1",
        "SESSION_2",
    }:
        print(
            f"PORTFOLIO MONITOR skipped: market state={market['state']}.",
            flush=True,
        )
        return

    # Core monitor keeps hard-stop/trailing/target logic. Structural daily/
    # weekly exits remain post-close to avoid treating an unfinished candle as
    # a confirmed bar.
    summary = monitor_swing_portfolio(
        allow_structural_exit=False
    )

    # New proactive layer: do not stay silent while an open real position is
    # already materially below its actual entry. It emits EXIT_WARNING /
    # EXIT_WARNING_STRONG and can escalate to CONFIRMED_SELL_EARLY when loss +
    # price structure agree.
    early_exit = monitor_early_exit_warnings()

    print(
        "SWING PORTFOLIO cycle complete: "
        + json.dumps(summary)
        + " | early_exit="
        + json.dumps(early_exit)
        + " | checks=SL/T1/T2/TRAILING/PROTECT_PROFIT/EARLY_EXIT"
        + " | structural daily/weekly exits=DEFERRED_TO_POST_CLOSE",
        flush=True,
    )


def main():
    run_portfolio_cycle()


if __name__ == "__main__":
    main()
