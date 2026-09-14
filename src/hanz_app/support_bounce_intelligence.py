"""HANZ intraday support-bounce intelligence.

Purpose
-------
Add a dedicated live-session detector for the question:
"Which IDX stocks are bouncing from support now?"

This module does not create a BUY by itself. It enriches the existing internal
predictive radar and leaves final user-facing BUY permission to the completed-bar
reconfirmation and risk gates already implemented by the swing engine.

Data policy
-----------
1. Keep the engine's intraday yfinance bars for 15m structure/history.
2. Cross-check/fallback the latest session snapshot with ZAPI IDX
   trading-info-daily when ZAPI_API_KEY is configured.
3. Never replace a fresh intraday bar merely because another provider differs.
   A material mismatch is flagged and blocks a support-bounce confirmation.
"""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from datetime import datetime


ZAPI_API_KEY = os.getenv("ZAPI_API_KEY", "").strip()
BOUNCE_MIN_RECOVERY_PCT = float(os.getenv("HANZ_BOUNCE_MIN_RECOVERY_PCT", "0.60"))
BOUNCE_MIN_CLOSE_LOCATION = float(os.getenv("HANZ_BOUNCE_MIN_CLOSE_LOCATION", "0.60"))
BOUNCE_MIN_PROJECTED_RVOL = float(os.getenv("HANZ_BOUNCE_MIN_PROJECTED_RVOL", "0.80"))
BOUNCE_MAX_PROVIDER_DIFF_PCT = float(os.getenv("HANZ_BOUNCE_MAX_PROVIDER_DIFF_PCT", "1.50"))
BOUNCE_SUPPORT_ATR_TOLERANCE = float(os.getenv("HANZ_BOUNCE_SUPPORT_ATR_TOLERANCE", "0.75"))
BOUNCE_SUPPORT_PCT_TOLERANCE = float(os.getenv("HANZ_BOUNCE_SUPPORT_PCT_TOLERANCE", "1.00"))


def _safe_float(value):
    try:
        if value is None:
            return None
        value = float(value)
        if value != value:
            return None
        return value
    except Exception:
        return None


def _clean_ticker(ticker):
    return str(ticker or "").upper().replace(".JK", "").strip()


def _pct_diff(a, b):
    a = _safe_float(a)
    b = _safe_float(b)
    if a is None or b is None:
        return None
    base = max(abs(a), abs(b), 1e-9)
    return abs(a - b) / base * 100.0


def _zapi_live_snapshot(engine, ticker):
    """Current-session IDX top-of-book/OHLC snapshot via ZAPI.

    The endpoint is a live daily trading snapshot, not a 15-minute history feed.
    It is therefore used only as a latest-price/session-OHLC verifier/fallback.
    """
    if not ZAPI_API_KEY:
        return None

    code = _clean_ticker(ticker)
    url = (
        "https://api.zpi.web.id/v1/finance:idx/trading-info-daily?"
        + urllib.parse.urlencode({"code": code})
    )
    req = urllib.request.Request(
        url,
        headers={"x-api-key": ZAPI_API_KEY, "accept": "application/json"},
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        payload = json.loads(resp.read().decode("utf-8"))

    if not isinstance(payload, dict):
        return None

    price = _safe_float(payload.get("close"))
    if price is None:
        return None

    now = engine.jakarta_now()
    market = engine.idx_market_session(now)
    session_state = str(market.get("state") or "")
    session_live = session_state in {
        "SESSION_1", "LUNCH_BREAK", "SESSION_2", "POST_CLOSE"
    }

    return {
        "price": price,
        "day_open": _safe_float(payload.get("open")),
        "day_high": _safe_float(payload.get("high")),
        "day_low": _safe_float(payload.get("low")),
        "volume_today": _safe_float(payload.get("volume")),
        "bid": _safe_float(payload.get("bid")),
        "offer": _safe_float(payload.get("offer")),
        "previous": _safe_float(payload.get("previous")),
        "value": _safe_float(payload.get("value")),
        "source": "ZAPI_IDX_TRADING_INFO_DAILY",
        "observed_at": now.isoformat(),
        "session_state": session_state,
        "session_live": session_live,
    }


def _projected_rvol(engine, completed_daily_df, volume_today):
    volume_today = _safe_float(volume_today)
    if volume_today is None or completed_daily_df is None or len(completed_daily_df) < 20:
        return None
    try:
        avg = _safe_float(completed_daily_df["Volume"].astype(float).iloc[-20:].mean())
    except Exception:
        return None
    if avg in (None, 0):
        return None
    progress = engine._idx_session_progress_fraction()
    expected = avg * max(progress, 0.15)
    if expected <= 0:
        return None
    return volume_today / expected


def _fallback_radar_snapshot(engine, ticker, completed_daily_df, daily, zapi):
    """Build a minimal radar snapshot when Yahoo intraday bars are unavailable."""
    if not zapi or not zapi.get("session_live"):
        raise RuntimeError("No fresh intraday source available")

    price = _safe_float(zapi.get("price"))
    prior_close = _safe_float(daily.get("price"))
    prior_high20 = _safe_float(daily.get("prior_high20"))
    day_open = _safe_float(zapi.get("day_open"))
    day_high = _safe_float(zapi.get("day_high"))
    day_low = _safe_float(zapi.get("day_low"))

    ret = None
    gap = None
    dist = None
    day_range = None
    if price is not None and prior_close not in (None, 0):
        ret = (price / prior_close - 1.0) * 100.0
    if day_open is not None and prior_close not in (None, 0):
        gap = (day_open / prior_close - 1.0) * 100.0
    if price is not None and prior_high20 not in (None, 0):
        dist = (prior_high20 - price) / prior_high20 * 100.0
    if price not in (None, 0) and day_high is not None and day_low is not None:
        day_range = (day_high - day_low) / abs(price) * 100.0

    return {
        "fresh": True,
        "age_minutes": 0.0,
        "source": zapi.get("source"),
        "bar_at": zapi.get("observed_at"),
        "price": price,
        "day_open": day_open,
        "day_high": day_high,
        "day_low": day_low,
        "volume_today": _safe_float(zapi.get("volume_today")),
        "session_progress": engine._idx_session_progress_fraction(),
        "projected_rvol": _projected_rvol(
            engine, completed_daily_df, zapi.get("volume_today")
        ),
        "intraday_return_pct": ret,
        "gap_pct": gap,
        "breakout_distance_pct": dist,
        "day_range_pct": day_range,
        "last_30m_return_pct": None,
        "intraday_volume_accel": None,
        "ema20": _safe_float(daily.get("ema20")),
        "prior_high20": prior_high20,
        "live_verifier": "ZAPI_IDX",
        "provider_diff_pct": None,
        "provider_mismatch": False,
        "fallback_live_source": True,
    }


def _support_bounce_fields(daily, snapshot):
    price = _safe_float(snapshot.get("price"))
    day_low = _safe_float(snapshot.get("day_low"))
    day_high = _safe_float(snapshot.get("day_high"))
    atr = _safe_float(daily.get("atr14"))

    candidates = [
        ("EMA20", _safe_float(daily.get("ema20"))),
        ("SWING_LOW", _safe_float(daily.get("last_swing_low"))),
        ("LOW_10D", _safe_float(daily.get("prior_low10"))),
        ("LOW_20D", _safe_float(daily.get("prior_low20"))),
        ("PREV_SWING_LOW", _safe_float(daily.get("prev_swing_low"))),
    ]
    usable = []
    for name, value in candidates:
        if value is None or price is None or value <= 0:
            continue
        # Support slightly above live price may still be a valid reclaim test.
        if value <= price * 1.015:
            usable.append((name, value))

    if not usable or price is None:
        return {
            "support_bounce_state": "NO_SUPPORT_DATA",
            "support_level": None,
            "support_type": None,
        }

    support_type, support = min(usable, key=lambda item: abs(price - item[1]))
    tolerance = max(
        (atr or 0.0) * BOUNCE_SUPPORT_ATR_TOLERANCE,
        support * BOUNCE_SUPPORT_PCT_TOLERANCE / 100.0,
    )

    touched = False
    if day_low is not None:
        touched = abs(day_low - support) <= tolerance
        if not touched and atr not in (None, 0):
            # Allow a shallow intraday undercut/reclaim, but not a breakdown.
            touched = support - 1.25 * atr <= day_low <= support + tolerance

    recovery_pct = None
    if day_low not in (None, 0) and price is not None:
        recovery_pct = (price / day_low - 1.0) * 100.0

    close_location = None
    if None not in (day_high, day_low, price) and day_high > day_low:
        close_location = (price - day_low) / (day_high - day_low)

    projected_rvol = _safe_float(snapshot.get("projected_rvol"))
    volume_accel = _safe_float(snapshot.get("intraday_volume_accel"))
    volume_ok = (
        (projected_rvol is not None and projected_rvol >= BOUNCE_MIN_PROJECTED_RVOL)
        or (volume_accel is not None and volume_accel >= 1.0)
        or (projected_rvol is None and volume_accel is None)
    )

    provider_mismatch = bool(snapshot.get("provider_mismatch"))
    reclaimed = price >= support
    recovery_ok = recovery_pct is not None and recovery_pct >= BOUNCE_MIN_RECOVERY_PCT
    location_ok = close_location is not None and close_location >= BOUNCE_MIN_CLOSE_LOCATION
    fresh = bool(snapshot.get("fresh"))

    if fresh and touched and reclaimed and recovery_ok and location_ok and volume_ok and not provider_mismatch:
        state = "BOUNCE_CONFIRMED"
    elif fresh and touched and not provider_mismatch:
        state = "BOUNCE_WATCH"
    else:
        state = "NO_BOUNCE"

    return {
        "support_bounce_state": state,
        "support_level": round(support, 4),
        "support_type": support_type,
        "support_distance_pct": round((price / support - 1.0) * 100.0, 3),
        "support_touch_tolerance": round(tolerance, 4),
        "support_touched": touched,
        "support_reclaimed": reclaimed,
        "bounce_recovery_pct": None if recovery_pct is None else round(recovery_pct, 3),
        "intraday_close_location": None if close_location is None else round(close_location, 4),
        "bounce_volume_ok": volume_ok,
    }


def install(engine):
    """Patch HANZ live quote + predictive radar with support-bounce intelligence."""
    original_latest_quote = engine.latest_intraday_quote
    original_snapshot = engine.intraday_radar_snapshot
    original_signal = engine.predictive_radar_signal

    def latest_quote_with_idx_fallback(ticker):
        yahoo = None
        yahoo_error = None
        try:
            yahoo = original_latest_quote(ticker)
        except Exception as exc:
            yahoo_error = str(exc)

        zapi = None
        try:
            zapi = _zapi_live_snapshot(engine, ticker)
        except Exception:
            zapi = None

        # Preserve a fresh bar from the existing intraday feed.
        if yahoo and yahoo.get("fresh_by_age"):
            if zapi:
                diff = _pct_diff(yahoo.get("price"), zapi.get("price"))
                yahoo["live_verifier"] = "ZAPI_IDX"
                yahoo["provider_diff_pct"] = None if diff is None else round(diff, 3)
                yahoo["provider_mismatch"] = bool(
                    diff is not None and diff > BOUNCE_MAX_PROVIDER_DIFF_PCT
                )
            return yahoo

        # If Yahoo has no fresh print, use the live IDX-derived observation.
        if zapi and zapi.get("session_live"):
            return {
                "price": zapi.get("price"),
                "bar_at": zapi.get("observed_at"),
                "age_minutes": 0.0,
                "fresh_by_age": True,
                "status": "OK_IDX_FALLBACK",
                "source": zapi.get("source"),
                "fallback_used": True,
                "attempt_errors": ([yahoo_error] if yahoo_error else []),
                "live_verifier": "ZAPI_IDX",
                "provider_diff_pct": _pct_diff(
                    (yahoo or {}).get("price"), zapi.get("price")
                ),
                "provider_mismatch": False,
            }

        if yahoo:
            return yahoo
        if yahoo_error:
            raise RuntimeError(yahoo_error)
        raise RuntimeError("No intraday market data")

    def snapshot_with_bounce(ticker, completed_daily_df, daily):
        zapi = None
        try:
            zapi = _zapi_live_snapshot(engine, ticker)
        except Exception:
            zapi = None

        try:
            snapshot = original_snapshot(ticker, completed_daily_df, daily)
        except Exception:
            snapshot = _fallback_radar_snapshot(
                engine, ticker, completed_daily_df, daily, zapi
            )

        if zapi:
            diff = _pct_diff(snapshot.get("price"), zapi.get("price"))
            snapshot["live_verifier"] = "ZAPI_IDX"
            snapshot["provider_diff_pct"] = None if diff is None else round(diff, 3)
            snapshot["provider_mismatch"] = bool(
                diff is not None and diff > BOUNCE_MAX_PROVIDER_DIFF_PCT
            )
            snapshot["idx_bid"] = zapi.get("bid")
            snapshot["idx_offer"] = zapi.get("offer")
            # A stale Yahoo session can safely fall back to the current IDX snapshot.
            if not snapshot.get("fresh") and zapi.get("session_live"):
                snapshot = _fallback_radar_snapshot(
                    engine, ticker, completed_daily_df, daily, zapi
                )
        else:
            snapshot.setdefault("live_verifier", None)
            snapshot.setdefault("provider_diff_pct", None)
            snapshot.setdefault("provider_mismatch", False)

        snapshot.update(_support_bounce_fields(daily, snapshot))
        return snapshot

    def signal_with_bounce(daily, weekly, snapshot):
        out = original_signal(daily, weekly, snapshot)
        evidence = list(out.get("evidence") or [])
        state = str(snapshot.get("support_bounce_state") or "NO_BOUNCE")

        if state == "BOUNCE_CONFIRMED":
            out["score"] = min(10, int(out.get("score") or 0) + 2)
            if out.get("state") in {"NO_SETUP", "RADAR_WATCH"}:
                out["state"] = "RADAR_PRE_ALERT"
            evidence.append(
                "BOUNCE: confirmed support reclaim at "
                f"{snapshot.get('support_type')} {snapshot.get('support_level')} | "
                f"recovery {snapshot.get('bounce_recovery_pct')}% | "
                f"close-location {snapshot.get('intraday_close_location')}"
            )
        elif state == "BOUNCE_WATCH":
            if out.get("state") == "NO_SETUP":
                out["state"] = "RADAR_WATCH"
            evidence.append(
                "BOUNCE_WATCH: support touched near "
                f"{snapshot.get('support_type')} {snapshot.get('support_level')} "
                "but recovery/volume confirmation is incomplete"
            )

        if snapshot.get("provider_mismatch"):
            out["armed"] = False
            evidence.append(
                "DATA_CAUTION: intraday providers differ by "
                f"{snapshot.get('provider_diff_pct')}%; bounce confirmation blocked"
            )

        out["evidence"] = evidence
        out["support_bounce_state"] = state
        out["support_level"] = snapshot.get("support_level")
        out["support_type"] = snapshot.get("support_type")
        out["bounce_recovery_pct"] = snapshot.get("bounce_recovery_pct")
        return out

    engine.latest_intraday_quote = latest_quote_with_idx_fallback
    engine.intraday_radar_snapshot = snapshot_with_bounce
    engine.predictive_radar_signal = signal_with_bounce

    print(
        "HANZ SUPPORT BOUNCE intelligence installed | "
        "intraday=15m structure + IDX live verifier/fallback | "
        "BUY remains completed-bar gated",
        flush=True,
    )
