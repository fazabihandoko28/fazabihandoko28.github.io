"""HANZ premarket radar with a strict PMR80 high-confidence gate.

Design
------
1. Always rank the best five available candidates from the latest completed
   session so the radar never goes blank merely because the strict setup is rare.
2. Only candidates that pass the empirically validated PMR80 rebound rule are
   labelled HIGH_CONFIDENCE_CALL.
3. Other rows are RADAR candidates, not 80%-validated predictions and not BUY
   confirmations.  Their score measures relative setup quality / proximity to
   the PMR80 pattern, not probability.

PMR80 validation target: next IDX session trades at least +1.0% above the signal
close.  Historical checks on the persisted HANZ chart cache produced 83.3% in a
prior ~45-day window (18 observations) and 86.4% in a recent ~45-day window
(22 observations) using the strict rule and Rp40B 20D average traded value gate.
"""

from __future__ import annotations


MODEL_VERSION = "PMR80_RADAR5_V3_2026_10_12"
TARGET_INTRADAY_UP_PCT = 1.0
REFERENCE_PRIOR_HIT_RATE_PCT = 83.3
REFERENCE_RECENT_HIT_RATE_PCT = 86.4
REFERENCE_MIN_HIT_RATE_PCT = 80.0

STRICT_MIN_AVG_VALUE20 = 40_000_000_000.0
RADAR_MIN_AVG_VALUE20 = 5_000_000_000.0
MAX_ROWS = 5

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
        "source_date": clean[-1]["time"],
        "price": price,
        "ret1_pct": 100.0 * (price / p1 - 1.0),
        "ret3_pct": 100.0 * (price / p3 - 1.0),
        "ret5_pct": 100.0 * (price / p5 - 1.0),
        "dist20_pct": 100.0 * (price / sma20 - 1.0),
        "rvol20": clean[-1]["volume"] / avgvol20,
        "avg_value20": avgval20,
    }


def _strict_qualifies(f):
    if not f:
        return False
    return bool(
        _num(f.get("avg_value20"), 0.0) >= STRICT_MIN_AVG_VALUE20
        and R1_MIN <= _num(f.get("ret1_pct"), 999.0) <= R1_MAX
        and R3_MIN <= _num(f.get("ret3_pct"), 999.0) <= R3_MAX
        and R5_MIN <= _num(f.get("ret5_pct"), 999.0) <= R5_MAX
        and DIST20_MIN <= _num(f.get("dist20_pct"), 999.0) <= DIST20_MAX
        and _num(f.get("rvol20"), 0.0) >= MIN_RVOL20
    )


def _distance_to_range(value, lo, hi):
    value = _num(value, 999.0)
    if lo <= value <= hi:
        return 0.0
    if value < lo:
        return lo - value
    return value - hi


def _radar_score(f):
    """Relative setup-quality score; it is NOT a probability."""
    if not f or _num(f.get("avg_value20"), 0.0) < RADAR_MIN_AVG_VALUE20:
        return None

    if _strict_qualifies(f):
        score = 90.0
        # Small tie-break rewards inside the validated zone.
        score += min(3.0, max(0.0, (_num(f.get("rvol20"), 0.8) - 0.8) * 2.0))
        if _num(f.get("avg_value20"), 0.0) >= 80_000_000_000:
            score += 2.0
        return int(min(99, round(score)))

    # Start from 75 and penalise distance from the validated rebound envelope.
    score = 75.0
    score -= min(18.0, _distance_to_range(f.get("ret1_pct"), R1_MIN, R1_MAX) * 3.0)
    score -= min(15.0, _distance_to_range(f.get("ret3_pct"), R3_MIN, R3_MAX) * 1.5)
    score -= min(15.0, _distance_to_range(f.get("ret5_pct"), R5_MIN, R5_MAX) * 1.0)
    score -= min(12.0, _distance_to_range(f.get("dist20_pct"), DIST20_MIN, DIST20_MAX) * 1.5)

    rvol = _num(f.get("rvol20"), 0.0)
    if rvol < MIN_RVOL20:
        score -= min(10.0, (MIN_RVOL20 - rvol) * 12.0)
    elif rvol <= 2.0:
        score += 2.0

    avgval = _num(f.get("avg_value20"), 0.0)
    if avgval >= 40_000_000_000:
        score += 6.0
    elif avgval >= 20_000_000_000:
        score += 4.0
    elif avgval >= 10_000_000_000:
        score += 2.0

    # Avoid ranking violent prior-day chases as bullish rebound candidates.
    if _num(f.get("ret1_pct"), 0.0) > 5.0:
        score -= 12.0
    if _num(f.get("ret5_pct"), 0.0) > 12.0:
        score -= 10.0

    return int(max(1, min(89, round(score))))


def _label(f, score):
    if _strict_qualifies(f):
        return "HIGH_CONFIDENCE_CALL_PMR80"
    if score >= 70:
        return "RADAR_NEAR_HIGH_CONF"
    if score >= 55:
        return "RADAR_CANDIDATE"
    return "RADAR_LOW_CONF"


def publish(engine):
    charts = engine.supabase_request(
        "GET",
        "hanz_swing_chart_data?select=ticker,source_bar_at,candles&limit=500",
    ) or []
    monitor_rows = engine.supabase_request(
        "GET",
        "hanz_swing_signal_monitor"
        "?select=ticker,state,price,sector,daily_trend,weekly_trend,daily_rsi,daily_rvol,entry_price,entry_low,entry_high,entry_status,stop_loss,target_1,target_2,risk_validation"
        "&limit=500",
    ) or []
    monitor = {str(r.get("ticker") or "").upper(): r for r in monitor_rows if r.get("ticker")}

    all_features = []
    source_dates = []
    for row in charts:
        f = _chart_features(row.get("candles"))
        ticker = str(row.get("ticker") or "").upper()
        if not f or not ticker:
            continue
        source_dates.append(f.get("source_date"))
        all_features.append((ticker, f))

    source_dates = [d for d in source_dates if d]
    source_date = max(source_dates) if source_dates else None

    candidates = []
    for ticker, f in all_features:
        if source_date and f.get("source_date") != source_date:
            continue
        score = _radar_score(f)
        if score is None:
            continue
        m = monitor.get(ticker) or {}
        rv = dict(m.get("risk_validation") or {})
        strict = _strict_qualifies(f)
        candidates.append({
            "ticker": ticker,
            "prediction_score": score,
            "prediction_label": _label(f, score),
            "price": f.get("price"),
            "state": m.get("state"),
            "daily_trend": m.get("daily_trend"),
            "weekly_trend": m.get("weekly_trend"),
            "sector": m.get("sector"),
            "daily_rsi": m.get("daily_rsi"),
            "daily_rvol": f.get("rvol20"),
            "ret1_pct": f.get("ret1_pct"),
            "ret3_pct": f.get("ret3_pct"),
            "ret5_pct": f.get("ret5_pct"),
            "avg_value20": f.get("avg_value20"),
            "median_value20": rv.get("median_value20"),
            "structure_state": rv.get("structure_state"),
            "setup_family": rv.get("setup_family"),
            "hanz_action": rv.get("hanz_action"),
            "entry_status": m.get("entry_status"),
            "entry_price": m.get("entry_price"),
            "entry_low": m.get("entry_low"),
            "entry_high": m.get("entry_high"),
            "stop_loss": m.get("stop_loss"),
            "target_1": m.get("target_1"),
            "target_2": m.get("target_2"),
            "source_bar_at": source_date,
            "reason": (
                ("PMR80 VALIDATED; " if strict else "RADAR ONLY; ")
                + f"1D {f['ret1_pct']:+.2f}%; 3D {f['ret3_pct']:+.2f}%; "
                + f"5D {f['ret5_pct']:+.2f}%; vs SMA20 {f['dist20_pct']:+.2f}%; "
                + f"RVOL {f['rvol20']:.2f}x; 20D value Rp{f['avg_value20']:,.0f}"
            ),
            "generated_at": engine.now_iso(),
        })

    candidates.sort(
        key=lambda r: (int(r.get("prediction_score") or 0), _num(r.get("avg_value20"), 0.0)),
        reverse=True,
    )

    payload = []
    for rank, row in enumerate(candidates[:MAX_ROWS], 1):
        item = dict(row)
        item["rank"] = rank
        payload.append(item)

    engine.supabase_request("DELETE", "hanz_premarket_bullish_current?rank=gte.1")
    if payload:
        engine.supabase_request(
            "POST", "hanz_premarket_bullish_current", payload=payload, prefer="return=minimal"
        )

    high_conf = sum(1 for r in payload if r.get("prediction_label") == "HIGH_CONFIDENCE_CALL_PMR80")
    return {
        "model": MODEL_VERSION,
        "published": len(payload),
        "source_date": source_date,
        "high_confidence_calls": high_conf,
        "top": [f"{r['ticker']}:{r['prediction_score']}:{r['prediction_label']}" for r in payload],
        "target_definition": f"PMR80 only: NEXT_SESSION_HIGH>={TARGET_INTRADAY_UP_PCT:.1f}%",
        "reference_validation": {
            "prior_window_hit_rate_pct": REFERENCE_PRIOR_HIT_RATE_PCT,
            "recent_window_hit_rate_pct": REFERENCE_RECENT_HIT_RATE_PCT,
            "minimum_required_pct": REFERENCE_MIN_HIT_RATE_PCT,
        },
        "doctrine": "ALWAYS_RANK_5_BUT_80PCT_CLAIM_ONLY_FOR_PMR80",
    }


def install(engine):
    original_run_cycle = engine.run_cycle

    def run_cycle_with_premarket_prediction():
        market = engine.idx_market_session()
        if market.get("state") in {"CLOSED_BEFORE_HOURS", "PRE_OPEN"}:
            summary = publish(engine)
            print("HANZ PREMARKET RADAR5: " + engine.json.dumps(summary, default=str), flush=True)
        return original_run_cycle()

    engine.run_cycle = run_cycle_with_premarket_prediction
    print(
        "HANZ PREMARKET RADAR5 installed | always ranks best five | PMR80 label reserved for validated setup | NOT BUY confirmation",
        flush=True,
    )
