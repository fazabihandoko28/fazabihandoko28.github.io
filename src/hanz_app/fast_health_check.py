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
    missing = []
    for ticker in sorted(tickers):
        # Consume this run's snapshot; do not retry an already missing ticker
        # immediately and accidentally turn a partial result into a feed outage.
        cached = engine._cached_market_frame(ticker, engine.INTRADAY_INTERVAL, engine.INTRADAY_PERIOD)
        if cached is None:
            missing.append(ticker)
            continue
        engine._record_market_bar(engine.normalize_ticker(ticker), engine.INTRADAY_INTERVAL, cached["frame"])
    written = engine.publish_cycle_health()
    rows = engine.supabase_request("GET", "hanz_fast_health?id=eq.bei-fast&select=*") or []
    row = rows[0] if rows else {}
    runtime_ok = bool(
        row.get("last_market_bar_at")
        and row.get("symbols_monitored") == len(engine._CYCLE_MARKET_BARS)
        and row.get("symbols_monitored", 0) > 0
        and row.get("last_scan_at") == written["last_scan_at"]
        and row.get("last_market_bar_at") == written["last_market_bar_at"]
        and row.get("data_status") == written["data_status"]
    )
    # Persisted candle evidence is not a PASS when its market data is stale.
    fresh = row.get("data_status") == "FRESH"
    verified = runtime_ok and fresh
    result = {
        "commit": os.getenv("GITHUB_SHA", "local"),
        "runtime_evidence": "PASS" if verified and not missing else ("PARTIAL" if verified else "FAIL"),
        "coverage_complete": not missing,
        "coverage_count": len(tickers) - len(missing),
        "universe_count": len(tickers),
        "missing_symbols": missing,
        "health": row,
    }
    print("HANZ FAST RUNTIME: " + json.dumps(result), flush=True)
    if not runtime_ok:
        raise RuntimeError("No persisted FAST candle evidence")
    if not fresh:
        raise RuntimeError(f"FAST intraday data not fresh: {row.get('data_status')}")
    if missing:
        raise RuntimeError(f"FAST coverage incomplete: {len(tickers) - len(missing)}/{len(tickers)}; missing={missing}")


if __name__ == "__main__":
    main()
