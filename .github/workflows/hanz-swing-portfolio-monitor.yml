import json

from .swing_trading_engine import (
    idx_market_session,
    jakarta_now,
    previous_idx_trading_day,
    next_idx_trading_day,
    monitor_swing_portfolio,
)


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

    # During the session we allow hard price/risk triggers, but defer
    # structural daily/weekly exits until completed post-close bars.
    summary = monitor_swing_portfolio(
        allow_structural_exit=False
    )

    print(
        "SWING PORTFOLIO cycle complete: "
        + json.dumps(summary)
        + " | checks=SL/T1/T2/TRAILING/PROTECT_PROFIT"
        + " | structural exits=DEFERRED_TO_POST_CLOSE",
        flush=True,
    )


def main():
    run_portfolio_cycle()


if __name__ == "__main__":
    main()
