"""Proactive intraday exit warnings for HANZ open swing positions.

This layer runs beside the existing hard-stop/trailing monitor.  Its job is to
warn before a hard stop when a real position is already losing and momentum is
deteriorating.  It never sends broker orders; it only updates HANZ portfolio
state and emits the existing HANZ alert/push pipeline.
"""

from . import swing_trading_engine as engine


WARNING_LOSS_PCT = -3.0
STRONG_WARNING_LOSS_PCT = -3.0
EARLY_SELL_LOSS_PCT = -4.5


def _f(v):
    return engine.safe_float(v)


def _position_signal(position, daily, live_price):
    avg_buy = _f(position.get("avg_buy"))
    stop = _f(position.get("stop_loss"))
    price = _f(live_price)
    if price is None or avg_buy in (None, 0):
        return None

    pnl = (price / avg_buy - 1.0) * 100.0
    if pnl > WARNING_LOSS_PCT:
        return None

    ema20 = _f(daily.get("ema20"))
    prior_low10 = _f(daily.get("prior_low10"))
    rsi = _f(daily.get("rsi14"))
    ret3 = _f(daily.get("ret3_pct"))

    below_ema20 = ema20 is not None and price < ema20
    broke_10d_support = prior_low10 is not None and price < prior_low10
    weak_rsi = rsi is not None and rsi < 48.0
    very_weak_rsi = rsi is not None and rsi < 45.0
    negative_3d = ret3 is not None and ret3 <= -2.0

    deterioration = sum([
        below_ema20,
        broke_10d_support,
        weak_rsi,
        negative_3d,
    ])

    # Hard stop remains the final risk line and is handled by the core engine.
    # This guard deliberately acts earlier only when price/momentum confirms
    # that the original setup is deteriorating.
    if (
        pnl <= EARLY_SELL_LOSS_PCT
        and below_ema20
        and (broke_10d_support or very_weak_rsi)
    ):
        return {
            "signal": "CONFIRMED_SELL_EARLY",
            "priority": 93,
            "pnl_pct": pnl,
            "reason": (
                f"Early exit confirmed: P/L {pnl:.2f}% from avg buy {avg_buy:.2f}, "
                "price is below EMA20 and momentum/support confirmation is bearish."
            ),
        }

    if pnl <= STRONG_WARNING_LOSS_PCT and deterioration >= 2:
        return {
            "signal": "EXIT_WARNING_STRONG",
            "priority": 86,
            "pnl_pct": pnl,
            "reason": (
                f"Prepare SELL: P/L {pnl:.2f}% from avg buy {avg_buy:.2f}; "
                f"{deterioration} momentum/support warnings are active."
            ),
        }

    # Even if technical damage has not fully confirmed yet, a 3% loss from
    # actual entry deserves a proactive warning instead of silent HOLD.
    return {
        "signal": "EXIT_WARNING",
        "priority": 78,
        "pnl_pct": pnl,
        "reason": (
            f"Exit watch: P/L {pnl:.2f}% from avg buy {avg_buy:.2f}. "
            "Position has crossed HANZ early-loss warning threshold; tighten risk and prepare exit if weakness confirms."
        ),
    }


def monitor_early_exit_warnings():
    positions = engine.fetch_swing_portfolio()
    summary = {"checked": 0, "warnings": 0, "confirmed_sell": 0, "errors": 0}

    for position in positions:
        ticker = position.get("ticker")
        portfolio_id = position.get("id")
        if not ticker:
            continue

        try:
            summary["checked"] += 1
            daily_df = engine.download_frame(
                ticker,
                engine.DAILY_INTERVAL,
                engine.DAILY_PERIOD,
            )
            daily = engine.daily_metrics(daily_df)

            live_price = None
            try:
                quote = engine.latest_intraday_quote(ticker)
                if quote and quote.get("fresh_by_age"):
                    live_price = quote.get("price")
            except Exception:
                pass
            if live_price is None:
                live_price = daily.get("price")

            result = _position_signal(position, daily, live_price)
            if not result:
                continue

            signal = result["signal"]
            if signal == "CONFIRMED_SELL_EARLY":
                summary["confirmed_sell"] += 1
            else:
                summary["warnings"] += 1

            updates = {
                "signal": signal,
                "last_price": live_price,
                "last_pnl_pct": result.get("pnl_pct"),
                "last_monitor_at": engine.now_iso(),
                "last_signal_reason": result.get("reason"),
            }
            if portfolio_id is not None:
                engine.update_swing_portfolio(portfolio_id, updates)
            position.update(updates)

            engine.insert_swing_alert(
                position=position,
                alert_type=signal,
                priority=result["priority"],
                message=(
                    f"{engine.clean_ticker(ticker)} price {float(live_price):.2f}. "
                    f"{result['reason']}"
                ),
                reason=result["reason"],
                daily_dedupe=True,
            )

            print(
                f"HANZ EARLY EXIT {engine.clean_ticker(ticker)} "
                f"signal={signal} pnl={result.get('pnl_pct'):.2f}% "
                f"reason={result.get('reason')}",
                flush=True,
            )

        except Exception as exc:
            summary["errors"] += 1
            print(
                f"HANZ EARLY EXIT {engine.clean_ticker(ticker)} failed: {exc}",
                flush=True,
            )

    return summary
