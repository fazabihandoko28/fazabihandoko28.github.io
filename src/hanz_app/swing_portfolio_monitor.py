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

    active_session = market["state"] in {
        "SESSION_1",
        "SESSION_2",
    }

    # Pre-open/lunch/post-close still run the proactive early-exit layer using
    # the latest completed daily data (and intraday only when the quote is fresh).
    # This prevents HANZ from staying silent overnight or before the next open.
    if not active_session:
        early_exit = monitor_early_exit_warnings()
        print(
            "SWING PORTFOLIO off-session health check complete: "
            + json.dumps(early_exit)
            + f" | market_state={market['state']}"
            + " | hard SL/trailing/target checks deferred to live session",
            flush=True,
        )
        return

    # During live sessions, keep hard-stop/trailing/target logic active.
    # Structural daily/weekly exits remain post-close to avoid treating an
    # unfinished candle as a confirmed bar.
    summary = monitor_swing_portfolio(
        allow_structural_exit=False
    )

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
