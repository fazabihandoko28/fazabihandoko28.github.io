"""HANZ market-data router and automatic data-quality gate.

Design:
- Daily primary: Index Alpha when INDEX_ALPHA_API_KEY is configured.
- Daily fallback: existing Yahoo/yfinance path.
- Independent IDX cross-check: Zapi stock-summary when ZAPI_API_KEY is configured.
- A material OHLC mismatch blocks real-money actionability and is carried into
  risk_validation so the single HANZ decision layer can reject the trade.

No provider key is ever exposed to the browser. Missing optional provider keys
never crash the scanner; HANZ falls back to Yahoo and marks verification status.
"""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

import pandas as pd


INDEX_ALPHA_API_KEY = os.getenv("INDEX_ALPHA_API_KEY", "").strip()
ZAPI_API_KEY = os.getenv("ZAPI_API_KEY", "").strip()
PRIMARY_MODE = os.getenv("HANZ_MARKET_DATA_PRIMARY", "AUTO").strip().upper()

# Price mismatches large enough to alter technical structure should block BUY.
CLOSE_MISMATCH_PCT = float(os.getenv("HANZ_DQ_CLOSE_MISMATCH_PCT", "0.75"))
OHLC_MISMATCH_PCT = float(os.getenv("HANZ_DQ_OHLC_MISMATCH_PCT", "1.50"))
VOLUME_CAUTION_PCT = float(os.getenv("HANZ_DQ_VOLUME_CAUTION_PCT", "50"))

_QUALITY_CACHE = {}


def _clean_ticker(ticker):
    return str(ticker or "").upper().replace(".JK", "").strip()


def _json_get(url, headers=None, timeout=20):
    req = urllib.request.Request(url, headers=headers or {}, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _pct_diff(a, b):
    try:
        a = float(a); b = float(b)
    except (TypeError, ValueError):
        return None
    base = max(abs(a), abs(b), 1e-9)
    return abs(a - b) / base * 100.0


def _period_start(period):
    p = str(period or "1y").lower()
    days = 370
    if p.endswith("mo"):
        try: days = max(35, int(p[:-2]) * 31 + 10)
        except Exception: pass
    elif p.endswith("y"):
        try: days = max(370, int(p[:-1]) * 366 + 10)
        except Exception: pass
    elif p.endswith("d"):
        try: days = max(35, int(p[:-1]) + 10)
        except Exception: pass
    return (datetime.utcnow().date() - timedelta(days=days)).isoformat()


def _index_alpha_daily_frame(ticker, period):
    if not INDEX_ALPHA_API_KEY:
        raise RuntimeError("INDEX_ALPHA_API_KEY not configured")
    symbol = _clean_ticker(ticker)
    params = urllib.parse.urlencode({
        "ticker": symbol,
        "from": _period_start(period),
        "to": datetime.utcnow().date().isoformat(),
    })
    payload = _json_get(
        f"https://api.indexalpha.id/stocks/ohlcv?{params}",
        headers={
            "accept": "application/json",
            "Authorization": f"Bearer {INDEX_ALPHA_API_KEY}",
        },
    )
    rows = payload.get("data") if isinstance(payload, dict) else None
    if not rows:
        raise RuntimeError("Index Alpha returned no OHLCV bars")
    df = pd.DataFrame(rows)
    rename = {
        "open": "Open", "high": "High", "low": "Low",
        "close": "Close", "volume": "Volume",
    }
    df = df.rename(columns=rename)
    needed = ["Open", "High", "Low", "Close"]
    if not all(c in df.columns for c in needed):
        raise RuntimeError("Index Alpha response missing OHLC columns")
    if "Volume" not in df.columns:
        df["Volume"] = 0
    df.index = pd.to_datetime(df["date"])
    df = df[["Open", "High", "Low", "Close", "Volume"]].apply(pd.to_numeric, errors="coerce")
    df = df.dropna(subset=needed).sort_index()
    if df.empty:
        raise RuntimeError("Index Alpha returned no usable bars")
    return df


def _zapi_stock_summary(ticker, date_value=None):
    if not ZAPI_API_KEY:
        return None
    params = {"length": 1, "start": 0, "code": _clean_ticker(ticker)}
    if date_value:
        params["date"] = str(date_value)[:10].replace("-", "")
    url = "https://api.zpi.web.id/v1/finance:idx/stock-summary?" + urllib.parse.urlencode(params)
    payload = _json_get(url, headers={"x-api-key": ZAPI_API_KEY, "accept": "application/json"})
    rows = payload.get("data") if isinstance(payload, dict) else None
    if not rows:
        return None
    row = rows[0]
    return {
        "date": str(row.get("Date") or "")[:10] or None,
        "open": row.get("OpenPrice") if row.get("OpenPrice") is not None else row.get("FirstTrade"),
        "high": row.get("High"),
        "low": row.get("Low"),
        "close": row.get("Close"),
        "volume": row.get("Volume"),
        "provider": str(payload.get("provider") or "IDX").upper(),
    }


def _latest_daily_snapshot(df):
    if df is None or df.empty:
        return None
    row = df.iloc[-1]
    idx = pd.Timestamp(df.index[-1])
    return {
        "date": idx.date().isoformat(),
        "open": float(row["Open"]),
        "high": float(row["High"]),
        "low": float(row["Low"]),
        "close": float(row["Close"]),
        "volume": float(row.get("Volume", 0) or 0),
    }


def _compare(primary, verifier):
    if not primary or not verifier:
        return {"status": "UNVERIFIED", "verified": False, "block": False, "reason": "Independent IDX verifier unavailable."}
    diffs = {k: _pct_diff(primary.get(k), verifier.get(k)) for k in ("open", "high", "low", "close")}
    close_diff = diffs.get("close")
    other = [diffs.get(k) for k in ("open", "high", "low") if diffs.get(k) is not None]
    max_other = max(other) if other else None
    volume_diff = _pct_diff(primary.get("volume"), verifier.get("volume"))
    block = (
        (close_diff is not None and close_diff > CLOSE_MISMATCH_PCT)
        or (max_other is not None and max_other > OHLC_MISMATCH_PCT)
    )
    caution = (not block and volume_diff is not None and volume_diff > VOLUME_CAUTION_PCT)
    if block:
        status = "MISMATCH"
        reason = f"OHLC mismatch: close {close_diff:.2f}% / max OHL {max_other:.2f}%. BUY blocked."
    elif caution:
        status = "VERIFIED_PRICE_VOLUME_CAUTION"
        reason = f"OHLC verified; volume differs {volume_diff:.1f}% across providers."
    else:
        status = "VERIFIED"
        reason = "Independent IDX OHLC cross-check passed."
    return {
        "status": status,
        "verified": not block,
        "block": block,
        "reason": reason,
        "ohlc_diff_pct": diffs,
        "volume_diff_pct": None if volume_diff is None else round(volume_diff, 2),
    }


def install(engine):
    """Patch engine data access/validation without changing core trading logic."""
    original_download = engine.download_frame
    original_validation = engine.real_money_validation

    def routed_download(ticker, interval, period):
        # Intraday and weekly remain on the existing feed. Index Alpha OHLCV is
        # end-of-day data and therefore only replaces the daily history path.
        use_index_alpha = str(interval).lower() == "1d" and INDEX_ALPHA_API_KEY and PRIMARY_MODE in {"AUTO", "INDEX_ALPHA"}
        if use_index_alpha:
            try:
                df = _index_alpha_daily_frame(ticker, period)
                snap = _latest_daily_snapshot(df)
                _QUALITY_CACHE[_clean_ticker(ticker)] = {
                    "primary_source": "INDEX_ALPHA_IDX_RAW",
                    "primary_snapshot": snap,
                    "fallback_used": False,
                }
                return df
            except Exception as exc:
                print(f"DATA ROUTER {_clean_ticker(ticker)} Index Alpha failed; fallback Yahoo: {exc}", flush=True)

        df = original_download(ticker, interval, period)
        if str(interval).lower() == "1d":
            _QUALITY_CACHE[_clean_ticker(ticker)] = {
                "primary_source": "YAHOO_FINANCE_FALLBACK" if INDEX_ALPHA_API_KEY else "YAHOO_FINANCE",
                "primary_snapshot": _latest_daily_snapshot(df),
                "fallback_used": bool(INDEX_ALPHA_API_KEY),
            }
        return df

    def validated_real_money(ticker, daily, result, levels, fundamental, context):
        rv = original_validation(ticker, daily, result, levels, fundamental, context)
        key = _clean_ticker(ticker)
        meta = dict(_QUALITY_CACHE.get(key) or {})
        primary = meta.get("primary_snapshot")
        if primary is None:
            # daily metrics always carry latest values, so preserve basic source
            # metadata even if this function is invoked outside normal scan flow.
            primary = {
                "date": str(daily.get("bar_at") or "")[:10] or None,
                "open": daily.get("open"), "high": daily.get("high"),
                "low": daily.get("low"), "close": daily.get("price"),
                "volume": daily.get("volume"),
            }
        verifier = None
        verifier_error = None
        if ZAPI_API_KEY:
            try:
                verifier = _zapi_stock_summary(key, primary.get("date"))
            except Exception as exc:
                verifier_error = str(exc)
        dq = _compare(primary, verifier)
        dq.update({
            "primary_source": meta.get("primary_source") or "YAHOO_FINANCE",
            "verifier_source": "ZAPI_IDX" if verifier is not None else None,
            "primary_date": primary.get("date") if primary else None,
            "verifier_date": verifier.get("date") if verifier else None,
            "fallback_used": bool(meta.get("fallback_used")),
            "verifier_error": verifier_error,
        })
        rv["data_quality"] = dq
        rv["data_quality_status"] = dq["status"]
        rv["data_primary_source"] = dq["primary_source"]
        rv["data_verifier_source"] = dq["verifier_source"]

        if dq.get("block"):
            rv["actionable"] = False
            rv["gate"] = "BLOCKED"
            blockers = list(rv.get("blockers") or [])
            if "DATA_MISMATCH" not in blockers:
                blockers.append("DATA_MISMATCH")
            rv["blockers"] = blockers
        elif dq["status"] == "VERIFIED_PRICE_VOLUME_CAUTION":
            cautions = list(rv.get("cautions") or [])
            if "VOLUME_PROVIDER_MISMATCH" not in cautions:
                cautions.append("VOLUME_PROVIDER_MISMATCH")
            rv["cautions"] = cautions

        return rv

    engine.download_frame = routed_download
    engine.real_money_validation = validated_real_money
    print(
        "HANZ DATA ROUTER installed | daily="
        + ("INDEX_ALPHA->YAHOO" if INDEX_ALPHA_API_KEY else "YAHOO")
        + " | verifier=" + ("ZAPI_IDX" if ZAPI_API_KEY else "NOT_CONFIGURED"),
        flush=True,
    )
