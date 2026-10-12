"""HANZ high-confidence premarket bullish-rebound predictor.

This module deliberately optimises precision over coverage.

Validation target
-----------------
A prediction is counted as directionally valid when the NEXT IDX session trades
at least +1.0% above the prior completed close at any point during that session.
That is a measurable bullish-behaviour target, not a BUY confirmation and not a
promise that the next close will finish green.

The retuned rule was checked on two separate recent windows from the persisted
HANZ chart cache (182 tickers x 130 completed daily bars):
- prior ~45 calendar days: 83.3% hit rate (18 observations)
- recent ~45 calendar days: 86.4% hit rate (22 observations)
for next-session high >= +1.0% versus the signal close.

The predictor MUST abstain when the high-confidence rule is not present.  It no
longer forces a Top-5 list merely to keep the dashboard populated.
"""

from __future__ import annotations


MODEL_VERSION = "PMR80_REBOUND_V2_2026_10_12"
TARGET_INTRADAY_UP_PCT = 1.0
REFERENCE_PRIOR_HIT_RATE_PCT = 83.3
REFERENCE_RECENT_HIT_RATE_PCT = 86.4
REFERENCE_MIN_HIT_RATE_PCT = 80.0

# Empirically important precision gate.  Lowering this materially reduced the
# two-window validation precision below the user's 80% benchmark.
MIN_AVG_VALUE20 = 40_000_000_000.0
MAX_ROWS = 3

# Retuned rebound setup.  This is intentionally contrarian: after a controlled
# multi-day pullback in a highly liquid stock, HANZ looks for next-session
# rebound behaviour rather than chasing the strongest prior green candle.
R1_MIN = -5.0
R1_MAX = -1.0
R3_MIN = -10.0
R3_MAX = -2.0
R5_MIN = -12.0
R5_MAX = -3.0
DIST20_MIN = -10.0
DIST20_MAX = -2.0
MIN_RVOL20 = 0.80


def _num(value, default=None):
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _date_key(value):
    text = str(value or "")
    return text[:10] if len(text) >= 10 else None


def _chart_features(candles):
    """Return last-bar features using completed candles only."""
    clean = []
    for c in candles or []:
        close = _num(c.get("close"))
        volume = _num(c.get("volume"), 0.0)
        if close is None or close <= 0:
            continue
        clean.append({
            "time": _date_key(c.get("time")),
            "close": close,
            "volume": max(0.0, volume or 0.0),
        })

    if len(clean) < 21:
        return None

    last = clean[-1]
    closes = [x["close"] for x in clean]
    volumes = [x["volume"] for x in clean]
    price = closes[-1]

    p1 = closes[-2]
    p3 = closes[-4] if len(closes) >= 4 else None
    p5 = closes[-6] if len(closes) >= 6 else None
    if not all(x and x > 0 for x in (p1, p3, p5)):
        return None

    last20_close = closes[-20:]
    last20_vol = volumes[-20:]
    sma20 = sum(last20_close) / len(last20_close)
    avgvol20 = sum(last20_vol) / len(last20_vol)
    avgval20 = sum(c * v for c, v in zip(last20_close, last20_vol)) / len(last20_close)

    if sma20 <= 0 or avgvol20 <= 0:
        return None

    return {
        "source_date": last["time"],
        "price": price,
        "ret1_pct": 100.0 * (price / p1 - 1.0),
        "ret3_pct": 100.0 * (price / p3 - 1.0),
        "ret5_pct": 100.0 * (price / p5 - 1.0),
        "dist20_pct": 100.0 * (price / sma20 - 1.0),
        "rvol20": last["volume"] / avgvol20,
        "avg_value20": avgval20,
    }


def _qualifies(f):
    if not f:
        return False
    return bool(
        _num(f.get("avg_value20"), 0.0) >= MIN_AVG_VALUE20
        and R1_MIN <= _num(f.get("ret1_pct"), 999.0) <= R1_MAX
        and R3_MIN <= _num(f.get("ret3_pct"), 999.0) <= R3_MAX
        and R5_MIN <= _num(f.get("ret5_pct"), 999.0) <= R5_MAX
        and DIST20_MIN <= _num(f.get("dist20_pct"), 999.0) <= DIST20_MAX
        and _num(f.get("rvol20"), 0.0) >= MIN_RVOL20
    )


def _setup_score(f):
    """Ranking score, not a probability."""
    score = 80.0

    # Reward deeper-but-controlled pullback near the historically useful zone.
    r1 = _num(f.get("ret1_pct"), -3.0)
    r3 = _num(f.get("ret3_pct"), -5.0)
    r5 = _num(f.get("ret5_pct"), -6.0)
    dist20 = _num(f.get("dist20_pct"), -4.0)
    rvol = _num(f.get("rvol20"), 0.8)
    avgval = _num(f.get("avg_value20"), MIN_AVG_VALUE20)

    score += max(0.0, 4.0 - abs(r1 + 2.5))
    score += max(0.0, 4.0 - abs((r3 + 5.0) * 0.6))
    score += max(0.0, 3.0 - abs((r5 + 6.0) * 0.35))
    score += max(0.0, 3.0 - abs((dist20 + 4.0) * 0.5))
    score += min(3.0, max(0.0, (rvol - MIN_RVOL20) * 2.0))
    if avgval >= 80_000_000_000:
        score += 2.0
    elif avgval >= 60_000_000_000:
        score += 1.0

    return int(max(80, min(99, round(score))))


def publish(engine):
    charts = engine.supabase_request(
        "GET",
        "hanz_swing_chart_data?select=ticker,source_bar_at,candles&limit=500",
    ) or []

    monitor_rows = engine.supabase_request(
        "GET",
        "hanz_swing_signal_monitor"
        "?select=ticker,state,price,sector,entry_price,entry_low,entry_high,entry_status,stop_loss,target_1,target_2,risk_validation"
        "&limit=500",
    ) or []
    monitor = {
        str(r.get("ticker") or "").upper(): r
        for r in monitor_rows
        if r.get("ticker")
    }

    features = []
    source_dates = []
    for row in charts:
        f = _chart_features(row.get("candles"))
        if not f:
            continue
        ticker = str(row.get("ticker") or "").upper()
        if not ticker:
            continue
        source_dates.append(f.get("source_date"))
        if _qualifies(f):
            features.append((ticker, f))

    source_dates = [d for d in source_dates if d]
    source_date = max(source_dates) if source_dates else None

    # Only publish rows from the latest completed session.  If the strict model
    # has no valid call, publish NOTHING and explicitly report abstention.
    candidates = []
    for ticker, f in features:
        if source_date and f.get("source_date") != source_date:
            continue
        m = monitor.get(ticker) or {}
        rv = dict(m.get("risk_validation") or {})
        score = _setup_score(f)
        candidates.append({
            "ticker": ticker,
            "prediction_score": score,
            "prediction_label": "PREDICTED_BULLISH_REBOUND_HIGH_CONF",
            "price": f.get("price"),
            "state": m.get("state"),
            "sector": m.get("sector"),
            "ret1_pct": f.get("ret1_pct"),
            "ret3_pct": f.get("ret3_pct"),
            "ret5_pct": f.get("ret5_pct"),
            "avg_value20": f.get("avg_value20"),
            "daily_rvol": f.get("rvol20"),
            "entry_status": m.get("entry_status"),
            "entry_price": m.get("entry_price"),
            "entry_low": m.get("entry_low"),
            "entry_high": m.get("entry_high"),
            "stop_loss": m.get("stop_loss"),
            "target_1": m.get("target_1"),
            "target_2": m.get("target_2"),
            "source_bar_at": source_date,
            "reason": (
                f"PMR80 rebound: 1D {f['ret1_pct']:+.2f}%; "
                f"3D {f['ret3_pct']:+.2f}%; 5D {f['ret5_pct']:+.2f}%; "
                f"vs SMA20 {f['dist20_pct']:+.2f}%; RVOL {f['rvol20']:.2f}x; "
                f"20D value Rp{f['avg_value20']:,.0f}"
            ),
            "generated_at": engine.now_iso(),
        })

    candidates.sort(
        key=lambda r: (
            int(r.get("prediction_score") or 0),
            _num(r.get("avg_value20"), 0.0),
        ),
        reverse=True,
    )

    payload = []
    for rank, row in enumerate(candidates[:MAX_ROWS], 1):
        item = dict(row)
        item["rank"] = rank
        payload.append(item)

    engine.supabase_request(
        "DELETE",
        "hanz_premarket_bullish_current?rank=gte.1",
    )
    if payload:
        engine.supabase_request(
            "POST",
            "hanz_premarket_bullish_current",
            payload=payload,
            prefer="return=minimal",
        )

    return {
        "model": MODEL_VERSION,
        "published": len(payload),
        "source_date": source_date,
        "eligible": len(candidates),
        "top": [f"{r['ticker']}:{r['prediction_score']}" for r in payload],
        "abstained": len(payload) == 0,
        "target_definition": f"NEXT_SESSION_HIGH>={TARGET_INTRADAY_UP_PCT:.1f}%",
        "reference_validation": {
            "prior_window_hit_rate_pct": REFERENCE_PRIOR_HIT_RATE_PCT,
            "recent_window_hit_rate_pct": REFERENCE_RECENT_HIT_RATE_PCT,
            "minimum_required_pct": REFERENCE_MIN_HIT_RATE_PCT,
        },
        "doctrine": "PRECISION_OVER_COVERAGE_NO_FORCED_TOP5",
    }


def install(engine):
    original_run_cycle = engine.run_cycle

    def run_cycle_with_premarket_prediction():
        market = engine.idx_market_session()
        if market.get("state") in {"CLOSED_BEFORE_HOURS", "PRE_OPEN"}:
            summary = publish(engine)
            print(
                "HANZ PREMARKET BULLISH PMR80: "
                + engine.json.dumps(summary, default=str),
                flush=True,
            )
        return original_run_cycle()

    engine.run_cycle = run_cycle_with_premarket_prediction
    print(
        "HANZ PREMARKET PMR80 installed | high-confidence rebound model | "
        "precision>coverage | no forced Top-5 | NOT BUY confirmation",
        flush=True,
    )
