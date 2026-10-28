"""Independent G1 FAST candle recovery evidence; never writes G0 or trading signals."""
from __future__ import annotations

import argparse
import json
import math
import re
import numpy as np
from urllib.request import Request, urlopen
from urllib.error import HTTPError
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
    # Providers may return out-of-order rows or malformed trailing rows.
    # Choose the newest actual valid timestamp, never the last row position.
    best = None
    for index in range(len(frame) - 1, -1, -1):
        try:
            bar = frame.iloc[index]
            # A provider boolean is not a genuine numeric OHLCV observation.
            if any(isinstance(bar[key], (bool, np.bool_))
                   for key in ("Open", "High", "Low", "Close", "Volume")):
                continue
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
            stamp = stamp.to_pydatetime().astimezone(timezone.utc)
            if best is None or stamp > best:
                best = stamp
        except (TypeError, ValueError, KeyError, AttributeError, OverflowError, IndexError):
            continue
    return best


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


def live_session_exit_code(result, enforce):
    """Gate G1 CI on independent genuine intraday evidence, not G0 health."""
    if not enforce or not result.get("idx_session_open"):
        return 0
    return 0 if (result.get("status") == "LIVE"
                 and result.get("fresh_valid_count", 0) >= G1_MIN_SYMBOLS
                 and result.get("universe_count") == G1_UNIVERSE_SIZE) else 2


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
                (not isinstance(prior, datetime) or prior.tzinfo is None or stamp > prior
                 or (prior.astimezone(timezone.utc) > now and _fresh_session_bar(stamp, now)))):
            bars[ticker] = stamp
    return bars



def _latest_direct_chart_bar(payload, symbol, now):
    """Verify actual Yahoo chart OHLCV, symbol identity and IDX timestamps."""
    try:
        result = payload["chart"]["result"][0]
        if str(result["meta"]["symbol"]).upper() != f"{symbol}.JK":
            return None
        quotes = result["indicators"]["quote"][0]
        stamps = result["timestamp"]
        fields = [quotes[key] for key in ("open", "high", "low", "close", "volume")]
        # zip() silently truncates mismatched provider arrays, potentially
        # attributing a volume/price to the wrong timestamp. Fail closed.
        if (not isinstance(stamps, list) or not stamps or
                any(not isinstance(values, list) or len(values) != len(stamps)
                    for values in fields)):
            return None
        best = None
        for stamp_s, opening, high, low, closing, volume in zip(stamps, *fields):
            if not isinstance(stamp_s, int) or isinstance(stamp_s, bool):
                continue
            # One malformed provider timestamp must not hide other genuine bars.
            try:
                stamp = datetime.fromtimestamp(stamp_s, timezone.utc)
            except (OverflowError, OSError, ValueError):
                continue
            if not _fresh_session_bar(stamp, now):
                continue
            # JSON true/false must never be coerced into prices or volume.
            if any(isinstance(value, bool)
                   for value in (opening, high, low, closing, volume)):
                continue
            try:
                prices = [float(x) for x in (opening, high, low, closing)]
                volume = float(volume)
            except (TypeError, ValueError, OverflowError):
                continue
            op, hi, lo, cl = prices
            if (not all(math.isfinite(v) and v > 0 for v in prices)
                    or not math.isfinite(volume) or volume <= 0
                    or not lo <= min(op, cl) <= max(op, cl) <= hi):
                continue
            if best is None or stamp > best:
                best = stamp
        return best
    except (KeyError, TypeError, ValueError, IndexError, OverflowError):
        return None


def _budgeted_direct_chart_symbols(missing, budget, now):
    """Rotate bounded retries by 30-minute slot; never starve later tickers."""
    if budget <= 0:
        return [], missing
    if len(missing) <= budget:
        return missing, []
    offset = (int(now.timestamp() // 1800) * budget) % len(missing)
    rotated = missing[offset:] + missing[:offset]
    return rotated[:budget], rotated[budget:]


def recover_missing_direct_chart(symbols, bars, now=None, opener=None, max_requests=40, diagnostics=None):
    """G1-only alternative to yfinance batches for still-unverified tickers.

    Fetches real Yahoo chart OHLCV via a separate HTTP path. Never writes G0,
    fabricates candles or upgrades a stale ticker without genuine evidence.
    """
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    now = now.astimezone(timezone.utc)
    missing = sorted(s for s in set(symbols)
                     if not _fresh_session_bar(bars.get(s), now))
    if not session_open(now):
        if diagnostics is not None:
            diagnostics.update({s: "idx_session_closed" for s in missing})
        return bars
    opener = opener or urlopen
    budget = max(0, max_requests)
    selected, deferred = _budgeted_direct_chart_symbols(missing, budget, now)
    if diagnostics is not None:
        diagnostics.update({s: "request_budget_exhausted" for s in deferred})
    for symbol in selected:
        if not isinstance(symbol, str) or not re.fullmatch(r"[A-Z0-9]{1,12}", symbol):
            if diagnostics is not None:
                diagnostics[symbol] = "invalid_symbol"
            continue
        request = Request(
            f"https://query2.finance.yahoo.com/v8/finance/chart/{symbol}.JK?interval=5m&range=1d",
            headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"},
        )
        try:
            with opener(request, timeout=8) as response:
                payload = json.load(response)
            stamp = _latest_direct_chart_bar(payload, symbol, now)
        except HTTPError as exc:
            if diagnostics is not None:
                diagnostics[symbol] = f"http_{exc.code}"
            continue
        except (OSError, ValueError, TypeError, KeyError, IndexError, OverflowError):
            if diagnostics is not None:
                diagnostics[symbol] = "provider_request_or_response_error"
            continue
        prior = bars.get(symbol)
        if (stamp is not None and
                (not isinstance(prior, datetime) or prior.tzinfo is None or stamp > prior
                 or (prior.astimezone(timezone.utc) > now and _fresh_session_bar(stamp, now)))):
            bars[symbol] = stamp
        if diagnostics is not None:
            diagnostics[symbol] = ("fresh_verified" if _fresh_session_bar(bars.get(symbol), now)
                                   else "no_fresh_valid_bar")
    return bars



def recover_missing_with_fallbacks(engine, symbols, bars, diagnostics=None):
    """Attempt real 5m bars, then independent direct chart even if 5m fails."""
    if diagnostics is None:
        diagnostics = {}
    try:
        recover_missing_five_minute_bars(engine, symbols, bars)
    except Exception as exc:
        # A failed optional provider must not prevent the independent retry.
        # Keep the error visible; only actual validated candles can count.
        diagnostics["five_minute_fallback_error"] = type(exc).__name__
    recover_missing_direct_chart(symbols, bars, diagnostics=diagnostics)
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
    # Closed-session probes cannot establish LIVE, so do not exhaust provider
    # requests on 198 symbols outside IDX hours. Preserve the actual universe.
    if not session_open(datetime.now(timezone.utc)):
        return evaluate_bars(symbols, {}, datetime.now(timezone.utc))
    attempts = {}
    try:
        engine.prefetch_market_data(symbols, engine.INTRADAY_INTERVAL, engine.INTRADAY_PERIOD)
    except Exception as exc:
        # Optional primary provider failure must not prevent independent fallbacks.
        attempts["one_minute_prefetch_error"] = type(exc).__name__
    bars = {}
    for ticker in symbols:
        try:
            cached = engine._cached_market_frame(ticker, engine.INTRADAY_INTERVAL, engine.INTRADAY_PERIOD)
            stamp = validated_bar(cached["frame"]) if cached else None
        except (OSError, ValueError, TypeError, KeyError, AttributeError, OverflowError, IndexError) as exc:
            # One broken cache entry must not block genuine 5m/direct-chart retries.
            attempts.setdefault("one_minute_cache_errors", {})[ticker] = type(exc).__name__
            continue
        if stamp is not None:
            bars[ticker] = stamp
    recover_missing_with_fallbacks(engine, symbols, bars, diagnostics=attempts)
    result = evaluate_bars(symbols, bars, datetime.now(timezone.utc))
    result["direct_chart_attempts"] = attempts
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fail-during-live-session", action="store_true")
    args = parser.parse_args()
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
    # A stale independent probe fails only during the live IDX session.
    # This exit code never certifies G1 CLOSED or changes G0.
    raise SystemExit(live_session_exit_code(result, args.fail_during_live_session))


if __name__ == "__main__":
    main()
