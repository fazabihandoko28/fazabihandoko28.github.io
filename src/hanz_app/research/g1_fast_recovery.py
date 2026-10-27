"""Independent G1 FAST candle recovery evidence; never writes G0 or trading signals."""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path

from hanz_app.research.g1_fast_live_evidence import (
    FRESHNESS_SECONDS, G1_MIN_SYMBOLS, G1_UNIVERSE_SIZE, session_open,
)

OUTPUT = Path("artifacts/g1/fast-recovery.json")


def validated_bar(frame):
    """Return the newest genuine valid OHLCV timestamp; never synthesize a bar."""
    if frame is None or frame.empty:
        return None
    # Providers can append a malformed trailing row. Retain the actual timestamp
    # of the newest earlier valid bar; freshness/session checks remain mandatory.
    for index in range(len(frame) - 1, -1, -1):
        try:
            bar = frame.iloc[index]
            prices = [float(bar[key]) for key in ("Open", "High", "Low", "Close")]
            opening, high, low, closing = prices
            volume = float(bar["Volume"])
            if (not all(math.isfinite(v) and v > 0 for v in prices)
                    or not math.isfinite(volume) or volume <= 0
                    or not low <= min(opening, closing) <= max(opening, closing) <= high):
                continue
            stamp = frame.index[index]
            if stamp.tzinfo is None:
                continue
            return stamp.to_pydatetime().astimezone(timezone.utc)
        except (TypeError, ValueError, KeyError, AttributeError, OverflowError, IndexError):
            continue
    return None


def evaluate_bars(tickers, bars, now):
    """No single newest candle can certify 190 independently fresh symbols."""
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    now = now.astimezone(timezone.utc)
    universe = sorted(set(tickers))
    valid = {}
    for symbol in universe:
        stamp = bars.get(symbol)
        if not isinstance(stamp, datetime) or stamp.tzinfo is None:
            continue
        stamp = stamp.astimezone(timezone.utc)
        age = (now - stamp).total_seconds()
        if 0 <= age <= FRESHNESS_SECONDS and session_open(stamp):
            valid[symbol] = stamp.isoformat()
    open_now = session_open(now)
    passed = (open_now and len(universe) == G1_UNIVERSE_SIZE
              and len(valid) >= G1_MIN_SYMBOLS)
    return {
        "generated_at": now.isoformat(),
        "status": "LIVE" if passed else "STALE",
        "source": "Yahoo intraday OHLCV (independent G1 read-only probe)",
        "idx_session_open": open_now,
        "universe_count": len(universe),
        "fresh_valid_count": len(valid),
        "required_fresh_count": G1_MIN_SYMBOLS,
        "universe_expected": G1_UNIVERSE_SIZE,
        "fresh_bar_timestamps": valid,
        "unverified_symbols": sorted(set(universe) - set(valid)),
        "g1_closed": False,
        "g0_touched": False,
    }



def _fresh_session_bar(stamp, now):
    """A valid 1m timestamp must also be fresh and from the regular IDX session."""
    if not isinstance(stamp, datetime) or stamp.tzinfo is None:
        return False
    age = (now - stamp.astimezone(timezone.utc)).total_seconds()
    return 0 <= age <= FRESHNESS_SECONDS and session_open(stamp)


def recover_missing_five_minute_bars(engine, symbols, bars, validate=validated_bar, now=None):
    """G1-only real 5m fallback for missing, stale or out-of-session 1m bars.

    A valid but old 1m bar must not prevent a genuine fresh 5m retry.
    Never invent candles or replace a newer bar with an older one.
    """
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    now = now.astimezone(timezone.utc)
    missing = sorted(symbol for symbol in set(symbols)
                     if not _fresh_session_bar(bars.get(symbol), now))
    if not missing:
        return bars
    engine.prefetch_market_data(missing, "5m", "5d")
    for ticker in missing:
        cached = engine._cached_market_frame(ticker, "5m", "5d")
        stamp = validate(cached["frame"]) if cached else None
        prior = bars.get(ticker)
        if (stamp is not None and
                (not isinstance(prior, datetime) or prior.tzinfo is None or stamp > prior)):
            bars[ticker] = stamp
    return bars


def collect():
    # Imports only here so pure validation tests never require live credentials.
    from hanz_app import fast_trading_engine as engine

    engine._CYCLE_PROVIDER_SUCCESSES = 0
    engine._CYCLE_PROVIDER_FAILURES = 0
    engine._CYCLE_MARKET_BARS.clear()
    symbols = set(engine.fetch_scout_universe())
    symbols.update(engine.clean_ticker(row.get("ticker")) for row in engine.fetch_watchlist())
    rows = engine.supabase_request("GET", "hanz_swing_signal_monitor?select=ticker&limit=1000") or []
    symbols.update(engine.clean_ticker(row.get("ticker")) for row in rows)
    symbols.discard("")
    symbols.discard(None)
    # A changed or empty universe cannot be used to certify 190/198.
    if len(symbols) != G1_UNIVERSE_SIZE:
        return evaluate_bars(symbols, {}, datetime.now(timezone.utc))
    engine.prefetch_market_data(symbols, engine.INTRADAY_INTERVAL, engine.INTRADAY_PERIOD)
    bars = {}
    for ticker in symbols:
        cached = engine._cached_market_frame(ticker, engine.INTRADAY_INTERVAL, engine.INTRADAY_PERIOD)
        stamp = validated_bar(cached["frame"]) if cached else None
        if stamp is not None:
            bars[ticker] = stamp
    recover_missing_five_minute_bars(engine, symbols, bars)
    return evaluate_bars(symbols, bars, datetime.now(timezone.utc))


def main():
    try:
        result = collect()
    except Exception as exc:
        result = evaluate_bars([], {}, datetime.now(timezone.utc))
        result["error"] = type(exc).__name__
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print("G1 INDEPENDENT FAST RECOVERY: " + json.dumps({
        key: value for key, value in result.items() if key != "fresh_bar_timestamps"
    }, sort_keys=True), flush=True)
    # STALE is evidence, not a failed software test. Downstream gates decide CLOSED.


if __name__ == "__main__":
    main()
