"""Run the FAST data path and persist candle evidence without generating alerts."""
import json
import os
from datetime import datetime, timezone

from hanz_app import fast_trading_engine as engine


def same_instant(left, right):
    """Compare UTC instants, not PostgREST's ISO formatting of microseconds."""
    if not left or not right:
        return False
    try:
        a = datetime.fromisoformat(str(left).replace("Z", "+00:00"))
        b = datetime.fromisoformat(str(right).replace("Z", "+00:00"))
    except (ValueError, TypeError, OverflowError):
        return False
    if a.tzinfo is None or b.tzinfo is None:
        return False
    return a.astimezone(timezone.utc) == b.astimezone(timezone.utc)


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
    expected_minimum = int(os.getenv("HANZ_EXPECTED_MIN_UNIVERSE", "198"))
    minimum_coverage = int(os.getenv("HANZ_MIN_COVERAGE", "190"))
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
    # Below-threshold coverage invalidates the snapshot. Missing symbols
    # above threshold remain explicitly reported without faking their bars.
    coverage_count = len(tickers) - len(missing)
    coverage_pass = coverage_count >= minimum_coverage
    if not coverage_pass or len(tickers) < expected_minimum:
        reason = (
            f"FAST coverage incomplete: {len(tickers) - len(missing)}/{len(tickers)}; "
            f"minimum universe={expected_minimum}; missing={missing}"
        )
        written = engine.update_fast_health(
            last_market_bar_at=written.get("last_market_bar_at"),
            data_status="PARTIAL",
            symbols_monitored=len(engine._CYCLE_MARKET_BARS),
            error="; ".join(part for part in (written.get("last_error"), reason) if part),
        )
    rows = engine.supabase_request("GET", "hanz_fast_health?id=eq.bei-fast&select=*") or []
    row = rows[0] if rows else {}
    runtime_ok = bool(
        row.get("last_market_bar_at")
        and row.get("symbols_monitored") == len(engine._CYCLE_MARKET_BARS)
        and row.get("symbols_monitored", 0) > 0
        and same_instant(row.get("last_scan_at"), written["last_scan_at"])
        and same_instant(row.get("last_market_bar_at"), written["last_market_bar_at"])
        and row.get("data_status") == written["data_status"]
    )
    # Persisted candle evidence is not a PASS when its market data is stale.
    # PARTIAL can mean a minority of symbols were unavailable. Accept the
    # configured coverage tolerance only when the oldest persisted candle is
    # independently within the strict freshness window. Never accept STALE.
    persisted_age = row.get("data_age_seconds")
    try:
        age_valid = (persisted_age is not None and
                     0 <= float(persisted_age) <= engine.MAX_DATA_AGE_SECONDS)
    except (TypeError, ValueError, OverflowError):
        age_valid = False
    fresh = (row.get("data_status") == "FRESH" or
             (row.get("data_status") == "PARTIAL" and coverage_pass and age_valid))
    universe_complete = len(tickers) >= expected_minimum
    verified = runtime_ok and fresh and universe_complete and coverage_pass
    result = {
        "commit": os.getenv("GITHUB_SHA", "local"),
        "runtime_evidence": "PASS" if verified else "FAIL",
        "coverage_complete": coverage_pass and universe_complete,
        "full_coverage": not missing and universe_complete,
        "minimum_coverage": minimum_coverage,
        "expected_minimum_universe": expected_minimum,
        "universe_complete": universe_complete,
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
    if not universe_complete:
        raise RuntimeError(f"FAST universe incomplete: {len(tickers)}/{expected_minimum} minimum")
    if not coverage_pass:
        raise RuntimeError(f"FAST coverage below minimum: {coverage_count}/{len(tickers)}; required={minimum_coverage}; missing={missing}")


if __name__ == "__main__":
    main()
