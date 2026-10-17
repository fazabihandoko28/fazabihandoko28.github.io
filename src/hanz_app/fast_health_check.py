"""Run the FAST data path and persist candle evidence without generating alerts."""
import json
import os

from hanz_app import fast_trading_engine as engine


def main():
    engine._CYCLE_PROVIDER_SUCCESSES = 0
    engine._CYCLE_PROVIDER_FAILURES = 0
    engine._CYCLE_MARKET_BARS.clear()
    tickers = set(engine.fetch_scout_universe())
    tickers.update(engine.clean_ticker(r.get("ticker")) for r in engine.fetch_watchlist())
    monitor = engine.supabase_request("GET", "hanz_swing_signal_monitor?select=ticker&limit=1000") or []
    tickers.update(engine.clean_ticker(r.get("ticker")) for r in monitor)
    tickers.discard("")
    tickers.discard(None)
    if not tickers:
        engine.update_fast_health(error="FAST runtime check: empty universe")
        raise RuntimeError("FAST runtime check: empty universe")
    engine.prefetch_market_data(tickers, engine.INTRADAY_INTERVAL, engine.INTRADAY_PERIOD)
    for ticker in sorted(tickers):
        try:
            engine.download_data(ticker, engine.INTRADAY_INTERVAL, engine.INTRADAY_PERIOD)
        except engine.MarketDataUnavailable as exc:
            print(f"FAST runtime missing {ticker}: {exc}", flush=True)
    engine.publish_cycle_health()
    rows = engine.supabase_request("GET", "hanz_fast_health?id=eq.bei-fast&select=*") or []
    row = rows[0] if rows else {}
    runtime_ok = bool(
        row.get("last_market_bar_at")
        and row.get("symbols_monitored") == len(engine._CYCLE_MARKET_BARS)
        and row.get("symbols_monitored", 0) > 0
    )
    result = {
        "commit": os.getenv("GITHUB_SHA", "local"),
        "runtime_evidence": "PASS" if runtime_ok else "FAIL",
        "universe_count": len(tickers),
        "health": row,
    }
    print("HANZ FAST RUNTIME: " + json.dumps(result), flush=True)
    if not runtime_ok:
        raise RuntimeError("No persisted FAST candle evidence")


if __name__ == "__main__":
    main()
