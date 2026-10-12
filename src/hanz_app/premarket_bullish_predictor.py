"""HANZ premarket bullish predictor.

Purpose
-------
Before IDX opens, rank stocks that have the strongest probability *proxy* for
bullish continuation/reversal today using only previously completed daily bars
already persisted in Supabase.

This is a predictive radar, NOT a BUY confirmation.  It deliberately keeps
"predicted direction" separate from "entry quality": a stock may rank bullish
while still being marked WAIT_PULLBACK / DO_NOT_CHASE.
"""

from __future__ import annotations

from datetime import datetime


MIN_AVG_VALUE = 5_000_000_000.0
MIN_MEDIAN_VALUE = 2_500_000_000.0
MIN_PREDICTION_SCORE = 60
MAX_ROWS = 5


def _num(value, default=None):
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _bool(value):
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _date_key(value):
    text = str(value or "")
    return text[:10] if len(text) >= 10 else None


def _prediction_score(row):
    rv = dict(row.get("risk_validation") or {})
    state = str(row.get("state") or "").upper()
    daily_trend = str(row.get("daily_trend") or "").upper()
    weekly_trend = str(row.get("weekly_trend") or "").upper()
    structure = str(rv.get("structure_state") or "").upper()
    momentum = str(rv.get("momentum_status") or "").upper()
    volatility = str(rv.get("volatility_status") or "").upper()
    action = str(rv.get("hanz_action") or "").upper()
    foreign = str(rv.get("foreign_flow_status") or "").upper()

    avg_value = _num(rv.get("avg_value20"), 0.0)
    median_value = _num(rv.get("median_value20"), 0.0)
    ret5 = _num(rv.get("ret5_pct"), 0.0)
    rsi = _num(row.get("daily_rsi"), 0.0)
    rvol = _num(row.get("daily_rvol"), 0.0)
    volume_accel = _num(rv.get("volume_accel_5d"), 0.0)

    # Hard quality filters.  Premarket ranking must never promote stale/illiquid
    # or structurally broken names merely because one recent candle was green.
    if state in {"MOMENTUM_BROKEN", "NO_SETUP"}:
        return None
    if momentum in {"BROKEN", "WEAKENING"}:
        return None
    if avg_value < MIN_AVG_VALUE or median_value < MIN_MEDIAN_VALUE:
        return None
    if daily_trend != "BULLISH" and weekly_trend != "BULLISH":
        return None
    if volatility == "EXTREME":
        return None
    if ret5 <= -2.0:
        return None

    score = 0
    reasons = []

    if daily_trend == "BULLISH":
        score += 10
        reasons.append("daily bullish")
    if weekly_trend == "BULLISH":
        score += 10
        reasons.append("weekly bullish")

    if structure == "BULLISH_HH_HL":
        score += 10
        reasons.append("HH/HL structure")
    elif structure == "MIXED":
        score += 5

    if state == "SETUP_READY":
        score += 10
        reasons.append("setup ready")
    elif state == "PRE_ALERT":
        score += 7
        reasons.append("pre-alert")
    elif state == "EARLY_WATCH":
        score += 4

    if _bool(rv.get("trigger_confirmed")):
        score += 7
        reasons.append("trigger confirmed")
    if _bool(rv.get("early_buy_gate")):
        score += 5
        reasons.append("early-reversal gate")
    if _bool(rv.get("higher_low")):
        score += 4

    if 50 <= rsi <= 68:
        score += 8
        reasons.append(f"RSI {rsi:.0f} healthy")
    elif 68 < rsi <= 75:
        score += 4
        reasons.append(f"RSI {rsi:.0f} warm")
    elif rsi < 50:
        score += 2

    if 1 <= ret5 <= 8:
        score += 8
        reasons.append(f"5D {ret5:+.1f}%")
    elif 8 < ret5 <= 12:
        score += 5
        reasons.append(f"5D {ret5:+.1f}% extended")
    elif ret5 > 12:
        score += 1
    elif ret5 > 0:
        score += 3

    if rvol >= 1.3:
        score += 7
        reasons.append(f"RVOL {rvol:.2f}x")
    elif rvol >= 1.0:
        score += 5
    elif rvol >= 0.7:
        score += 2

    if volume_accel >= 1.2:
        score += 4
    elif volume_accel >= 1.0:
        score += 2

    # Both liquidity gates already passed above; reward consistent capacity.
    score += 8

    if foreign in {"ACCUMULATING", "MILD_ACCUMULATION", "STRONG_ACCUMULATION"}:
        score += 4
        reasons.append("foreign accumulation")
    elif foreign in {"CAUTION", "DISTRIBUTING", "DISTRIBUTION_WATCH"}:
        score -= 3

    if volatility == "HIGH":
        score -= 6
    else:
        score += 3

    # Direction can remain bullish even when entry is poor.  Penalise chasing,
    # but do not erase a genuine bullish prediction solely because price is
    # extended; the dashboard will show WAIT_PULLBACK separately.
    if _bool(rv.get("do_not_chase")):
        score -= 8
        reasons.append("extended / wait pullback")
    if action == "TP_RISK":
        score -= 8
    if _bool(rv.get("resistance_capped")):
        score -= 6
        reasons.append("near resistance")

    if momentum == "HEALTHY":
        score += 4

    score = int(max(0, min(100, score)))
    return score, reasons


def _label(score):
    if score >= 80:
        return "PREDICTED_BULLISH_HIGH"
    if score >= 70:
        return "PREDICTED_BULLISH"
    return "WATCH_BULLISH"


def publish(engine):
    rows = engine.supabase_request(
        "GET",
        "hanz_swing_signal_monitor"
        "?select=ticker,state,score,price,daily_trend,weekly_trend,daily_rsi,daily_rvol,"
        "sector,daily_bar_at,entry_price,entry_low,entry_high,entry_status,stop_loss,target_1,target_2,risk_validation"
        "&limit=500",
    ) or []

    dates = [_date_key(r.get("daily_bar_at")) for r in rows]
    dates = [d for d in dates if d]
    if not dates:
        return {"published": 0, "reason": "no completed-bar monitor rows"}

    source_date = max(dates)
    candidates = []
    for row in rows:
        if _date_key(row.get("daily_bar_at")) != source_date:
            continue
        result = _prediction_score(row)
        if result is None:
            continue
        score, reasons = result
        if score < MIN_PREDICTION_SCORE:
            continue

        rv = dict(row.get("risk_validation") or {})
        candidates.append({
            "ticker": str(row.get("ticker") or "").upper(),
            "prediction_score": score,
            "prediction_label": _label(score),
            "price": row.get("price"),
            "state": row.get("state"),
            "daily_trend": row.get("daily_trend"),
            "weekly_trend": row.get("weekly_trend"),
            "sector": row.get("sector"),
            "daily_rsi": row.get("daily_rsi"),
            "daily_rvol": row.get("daily_rvol"),
            "ret1_pct": rv.get("ret1_pct"),
            "ret3_pct": rv.get("ret3_pct"),
            "ret5_pct": rv.get("ret5_pct"),
            "avg_value20": rv.get("avg_value20"),
            "median_value20": rv.get("median_value20"),
            "structure_state": rv.get("structure_state"),
            "setup_family": rv.get("setup_family"),
            "hanz_action": rv.get("hanz_action"),
            "entry_status": row.get("entry_status"),
            "entry_price": row.get("entry_price"),
            "entry_low": row.get("entry_low"),
            "entry_high": row.get("entry_high"),
            "stop_loss": row.get("stop_loss"),
            "target_1": row.get("target_1"),
            "target_2": row.get("target_2"),
            "source_bar_at": row.get("daily_bar_at"),
            "reason": "; ".join(reasons[:7]),
            "generated_at": engine.now_iso(),
        })

    candidates.sort(
        key=lambda r: (
            int(r.get("prediction_score") or 0),
            _num(r.get("median_value20"), 0.0),
        ),
        reverse=True,
    )
    payload = []
    for rank, row in enumerate(candidates[:MAX_ROWS], 1):
        item = dict(row)
        item["rank"] = rank
        payload.append(item)

    # Current snapshot table: replace prior morning's ranking atomically enough
    # for this small 5-row dataset.  Failure leaves an explicit exception in CI.
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
        "published": len(payload),
        "source_date": source_date,
        "eligible": len(candidates),
        "top": [f"{r['ticker']}:{r['prediction_score']}" for r in payload],
        "doctrine": "PREDICTION_ONLY_NOT_BUY_CONFIRMATION",
    }


def install(engine):
    original_run_cycle = engine.run_cycle

    def run_cycle_with_premarket_prediction():
        market = engine.idx_market_session()
        if market.get("state") in {"CLOSED_BEFORE_HOURS", "PRE_OPEN"}:
            summary = publish(engine)
            print(
                "HANZ PREMARKET BULLISH: "
                + engine.json.dumps(summary, default=str),
                flush=True,
            )
        return original_run_cycle()

    engine.run_cycle = run_cycle_with_premarket_prediction
    print(
        "HANZ PREMARKET PREDICTOR installed | prior completed bars -> Top-5 bullish radar | NOT BUY confirmation",
        flush=True,
    )
