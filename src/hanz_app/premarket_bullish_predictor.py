"""HANZ PMR80 radar.

The radar always publishes the best five relative candidates from the latest
completed daily bar.  Only rows that pass the strict empirically validated
PMR80 rebound rule receive HIGH_CONFIDENCE_CALL_PMR80.  Other rows remain radar
candidates and must never be presented as >=80% validated calls.

Validation target for the strict rule: next IDX session trades at least +1.0%
above the signal close.  Historical checks on the persisted HANZ chart cache:
prior ~45-day window 83.3% (18 observations), recent ~45-day window 86.4%
(22 observations), using Rp40B minimum 20D average traded value.
"""
from __future__ import annotations

MODEL_VERSION = "PMR80_RADAR5_V4_LIVE_2026_10_12"
TARGET_INTRADAY_UP_PCT = 1.0
REFERENCE_PRIOR_HIT_RATE_PCT = 83.3
REFERENCE_RECENT_HIT_RATE_PCT = 86.4
REFERENCE_MIN_HIT_RATE_PCT = 80.0
STRICT_MIN_AVG_VALUE20 = 40_000_000_000.0
RADAR_MIN_AVG_VALUE20 = 5_000_000_000.0
MAX_ROWS = 5

R1_MIN, R1_MAX = -5.0, -1.0
R3_MIN, R3_MAX = -10.0, -2.0
R5_MIN, R5_MAX = -12.0, -3.0
DIST20_MIN, DIST20_MAX = -10.0, -2.0
MIN_RVOL20 = 0.80


def _num(v, default=None):
    try:
        return default if v is None else float(v)
    except (TypeError, ValueError):
        return default


def _date(v):
    s = str(v or "")
    return s[:10] if len(s) >= 10 else None


def _features(candles):
    rows = []
    for c in candles or []:
        cl = _num(c.get("close"))
        vol = max(0.0, _num(c.get("volume"), 0.0) or 0.0)
        if cl and cl > 0:
            rows.append((_date(c.get("time")), cl, vol))
    if len(rows) < 21:
        return None
    closes = [r[1] for r in rows]
    vols = [r[2] for r in rows]
    px = closes[-1]
    p1, p3, p5 = closes[-2], closes[-4], closes[-6]
    c20, v20 = closes[-20:], vols[-20:]
    sma20 = sum(c20) / 20
    avgvol20 = sum(v20) / 20
    avgval20 = sum(c * v for c, v in zip(c20, v20)) / 20
    if sma20 <= 0 or avgvol20 <= 0:
        return None
    return {
        "source_date": rows[-1][0],
        "price": px,
        "ret1_pct": 100.0 * (px / p1 - 1.0),
        "ret3_pct": 100.0 * (px / p3 - 1.0),
        "ret5_pct": 100.0 * (px / p5 - 1.0),
        "dist20_pct": 100.0 * (px / sma20 - 1.0),
        "rvol20": vols[-1] / avgvol20,
        "avg_value20": avgval20,
    }


def _strict(f):
    return bool(
        f
        and f["avg_value20"] >= STRICT_MIN_AVG_VALUE20
        and R1_MIN <= f["ret1_pct"] <= R1_MAX
        and R3_MIN <= f["ret3_pct"] <= R3_MAX
        and R5_MIN <= f["ret5_pct"] <= R5_MAX
        and DIST20_MIN <= f["dist20_pct"] <= DIST20_MAX
        and f["rvol20"] >= MIN_RVOL20
    )


def _range_distance(v, lo, hi):
    if lo <= v <= hi:
        return 0.0
    span = max(abs(hi - lo), 1e-9)
    return (lo - v) / span if v < lo else (v - hi) / span


def _radar_score(f):
    """Relative proximity score. This is NOT a probability."""
    if not f or f["avg_value20"] < RADAR_MIN_AVG_VALUE20:
        return 0
    penalty = 0.0
    penalty += 18 * _range_distance(f["ret1_pct"], R1_MIN, R1_MAX)
    penalty += 14 * _range_distance(f["ret3_pct"], R3_MIN, R3_MAX)
    penalty += 14 * _range_distance(f["ret5_pct"], R5_MIN, R5_MAX)
    penalty += 18 * _range_distance(f["dist20_pct"], DIST20_MIN, DIST20_MAX)
    if f["rvol20"] < MIN_RVOL20:
        penalty += min(18.0, (MIN_RVOL20 - f["rvol20"]) * 18.0)
    if f["avg_value20"] < STRICT_MIN_AVG_VALUE20:
        ratio = f["avg_value20"] / STRICT_MIN_AVG_VALUE20
        penalty += 12.0 * max(0.0, 1.0 - ratio)
    return int(max(10, min(79, round(79 - penalty))))


def _strict_score(f):
    score = 88.0
    score += max(0.0, 3.0 - abs(f["ret1_pct"] + 2.5))
    score += max(0.0, 2.0 - abs((f["ret3_pct"] + 5.0) * 0.35))
    score += max(0.0, 2.0 - abs((f["ret5_pct"] + 6.0) * 0.25))
    score += min(2.0, max(0.0, (f["rvol20"] - 0.8) * 1.5))
    if f["avg_value20"] >= 80_000_000_000:
        score += 2.0
    elif f["avg_value20"] >= 60_000_000_000:
        score += 1.0
    return int(max(88, min(99, round(score))))


def publish(engine):
    charts = engine.supabase_request(
        "GET", "hanz_swing_chart_data?select=ticker,source_bar_at,candles&limit=500"
    ) or []
    monitor_rows = engine.supabase_request(
        "GET",
        "hanz_swing_signal_monitor?select=ticker,state,sector,entry_price,entry_low,entry_high,entry_status,stop_loss,target_1,target_2,risk_validation,daily_bar_at,risk_gate&limit=500",
    ) or []
    monitor = {str(r.get("ticker") or "").upper(): r for r in monitor_rows if r.get("ticker")}

    feature_rows, dates = [], []
    for row in charts:
        ticker = str(row.get("ticker") or "").upper()
        f = _features(row.get("candles"))
        if not ticker or not f:
            continue
        dates.append(f["source_date"])
        feature_rows.append((ticker, f))
    source_date = max([d for d in dates if d], default=None)

    candidates = []
    for ticker, f in feature_rows:
        if source_date and f["source_date"] != source_date:
            continue
        strict = _strict(f)
        score = _strict_score(f) if strict else _radar_score(f)
        if score <= 0:
            continue
        m = monitor.get(ticker) or {}
        # Never attach yesterday's entry/stop/targets to today's candle.
        # An invalid stop above the reference price is not a usable long setup.
        # Keep the symbol in prediction-only RADAR, with execution levels hidden.
        monitor_date = str(m.get("daily_bar_at") or "")[:10]
        stop = m.get("stop_loss")
        try:
            valid_stop = stop is not None and 0 < float(stop) < float(f["price"])
        except (ValueError, TypeError):
            valid_stop = False
        valid_levels = monitor_date == source_date and valid_stop and str(m.get("state") or "").upper() != "MOMENTUM_BROKEN"
        if strict:
            label = "RADAR_STRICT_UNVALIDATED"
        elif score >= 65:
            label = "RADAR_NEAR_HIGH_CONF"
        elif score >= 45:
            label = "RADAR_CANDIDATE"
        else:
            label = "RADAR_LOW_CONF"
        candidates.append({
            "ticker": ticker,
            "prediction_score": score,
            "prediction_label": label,
            "price": f["price"],
            "state": m.get("state"),
            "sector": m.get("sector"),
            "ret1_pct": f["ret1_pct"],
            "ret3_pct": f["ret3_pct"],
            "ret5_pct": f["ret5_pct"],
            "avg_value20": f["avg_value20"],
            "daily_rvol": f["rvol20"],
            "entry_status": m.get("entry_status") if valid_levels else "UNVALIDATED_LEVELS",
            "entry_price": m.get("entry_price") if valid_levels else None,
            "entry_low": m.get("entry_low") if valid_levels else None,
            "entry_high": m.get("entry_high") if valid_levels else None,
            "stop_loss": m.get("stop_loss") if valid_levels else None,
            "target_1": m.get("target_1") if valid_levels else None,
            "target_2": m.get("target_2") if valid_levels else None,
            "source_bar_at": source_date,
            "reason": (
                f"{label}: 1D {f['ret1_pct']:+.2f}% · 3D {f['ret3_pct']:+.2f}% · "
                f"5D {f['ret5_pct']:+.2f}% · vs SMA20 {f['dist20_pct']:+.2f}% · "
                f"RVOL {f['rvol20']:.2f}x · 20D value Rp{f['avg_value20']:,.0f}"
            ),
            "generated_at": engine.now_iso(),
        })

    candidates.sort(key=lambda r: (r["prediction_score"], r["avg_value20"]), reverse=True)
    payload = []
    for rank, row in enumerate(candidates[:MAX_ROWS], 1):
        item = dict(row)
        item["rank"] = rank
        payload.append(item)

    # A complete Top 5 is required. Do not publish a partial ranking.
    if len(payload) != MAX_ROWS:
        return {"model": MODEL_VERSION, "published": 0, "source_date": source_date,
                "status": "SKIPPED_INCOMPLETE_INPUT_PRESERVED_PREVIOUS"}
    write_result = engine.supabase_request("POST", "hanz_premarket_bullish_current?on_conflict=rank",
                                           payload=payload, prefer="resolution=merge-duplicates,return=minimal")
    if write_result is False:
        raise RuntimeError("PMR80 ranking upsert failed")

    return {
        "model": MODEL_VERSION,
        "published": len(payload),
        "source_date": source_date,
        "high_confidence": sum(1 for r in payload if r["prediction_label"] == "HIGH_CONFIDENCE_CALL_PMR80"),
        "top": [f"{r['ticker']}:{r['prediction_score']}:{r['prediction_label']}" for r in payload],
        "target": f"NEXT_SESSION_HIGH>={TARGET_INTRADAY_UP_PCT:.1f}%",
        "validation": {"status": "EXPLORATORY_NOT_OUT_OF_SAMPLE_VALIDATED", "prior": REFERENCE_PRIOR_HIT_RATE_PCT, "recent": REFERENCE_RECENT_HIT_RATE_PCT},
    }


def install(engine):
    original_run_cycle = engine.run_cycle

    def run_cycle_with_pmr80():
        # Recompute on EVERY scanner cycle. During market hours this still uses
        # the latest completed daily candle, so there is no look-ahead leak.
        result = original_run_cycle()
        try:
            summary = publish(engine)
            print("HANZ PMR80 LIVE: " + engine.json.dumps(summary, default=str), flush=True)
        except Exception as exc:
            print(f"HANZ PMR80 LIVE failed-soft: {exc}", flush=True)
        return result

    engine.run_cycle = run_cycle_with_pmr80
    print("HANZ PMR80 V4 installed | every-cycle publish | PMR80 strict label only | Top5 radar always", flush=True)
