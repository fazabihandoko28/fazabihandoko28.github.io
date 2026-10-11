"""HANZ V12 context-quality overlay.

Strengthens four areas without changing the core setup doctrine:
1) Liquidity quality: median traded value + consistency, not average alone.
2) Market regime: IHSG structure blended with broad-universe breadth.
3) Sector regime: sector breadth + stock relative-strength override.
4) Context telemetry: expose breadth/sector quality to ranking and dashboard.

The overlay is deliberately fail-soft. Missing breadth/sector data never invents a
signal and never upgrades a weak market; it falls back to the core engine.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone


MIN_MEDIAN_DAILY_VALUE_IDR = float(
    os.getenv("HANZ_MIN_MEDIAN_DAILY_VALUE_IDR", "2500000000")
)
MIN_LIQUIDITY_CONSISTENCY = float(
    os.getenv("HANZ_MIN_LIQUIDITY_CONSISTENCY", "0.35")
)
LIQUIDITY_CAUTION_CONSISTENCY = float(
    os.getenv("HANZ_LIQUIDITY_CAUTION_CONSISTENCY", "0.50")
)
BREADTH_MAX_AGE_DAYS = int(os.getenv("HANZ_BREADTH_MAX_AGE_DAYS", "7"))
SECTOR_MIN_SAMPLE = int(os.getenv("HANZ_SECTOR_MIN_SAMPLE", "3"))
SECTOR_BLOCK_SCORE = float(os.getenv("HANZ_SECTOR_BLOCK_SCORE", "20"))
SECTOR_WEAK_SCORE = float(os.getenv("HANZ_SECTOR_WEAK_SCORE", "40"))
SECTOR_STRONG_SCORE = float(os.getenv("HANZ_SECTOR_STRONG_SCORE", "65"))
SECTOR_RS_OVERRIDE_PCT = float(os.getenv("HANZ_SECTOR_RS_OVERRIDE_PCT", "3.0"))


def _num(value, default=None):
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _fresh_enough(value):
    if not value:
        return True
    try:
        ts = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - ts.astimezone(timezone.utc)).total_seconds()
        return age <= BREADTH_MAX_AGE_DAYS * 86400
    except Exception:
        return True


def _pct(numerator, denominator):
    if denominator <= 0:
        return None
    return numerator / denominator * 100.0


def _bucket_score(rows):
    """Breadth score from already-persisted completed-bar monitor rows."""
    if not rows:
        return {
            "score": None,
            "sample": 0,
            "daily_bullish_pct": None,
            "weekly_bullish_pct": None,
            "positive_ret5_pct": None,
            "healthy_momentum_pct": None,
            "avg_ret5_pct": None,
        }

    daily_valid = [r for r in rows if r.get("daily_trend")]
    weekly_valid = [r for r in rows if r.get("weekly_trend")]

    daily_bull = sum(
        1 for r in daily_valid
        if str(r.get("daily_trend") or "").upper() == "BULLISH"
    )
    weekly_bull = sum(
        1 for r in weekly_valid
        if str(r.get("weekly_trend") or "").upper() == "BULLISH"
    )

    ret5_values = []
    healthy_values = []
    for row in rows:
        rv = row.get("risk_validation") or {}
        ret5 = _num(rv.get("ret5_pct"))
        if ret5 is not None:
            ret5_values.append(ret5)
        status = str(rv.get("momentum_status") or "").upper()
        if status:
            healthy_values.append(status == "HEALTHY")

    daily_pct = _pct(daily_bull, len(daily_valid))
    weekly_pct = _pct(weekly_bull, len(weekly_valid))
    positive_ret5_pct = _pct(sum(1 for x in ret5_values if x > 0), len(ret5_values))
    healthy_pct = _pct(sum(1 for x in healthy_values if x), len(healthy_values))

    components = []
    if daily_pct is not None:
        components.append((daily_pct, 0.35))
    if weekly_pct is not None:
        components.append((weekly_pct, 0.25))
    if positive_ret5_pct is not None:
        components.append((positive_ret5_pct, 0.20))
    if healthy_pct is not None:
        components.append((healthy_pct, 0.20))

    if components:
        weight = sum(w for _, w in components)
        score = sum(v * w for v, w in components) / weight
    else:
        score = None

    return {
        "score": None if score is None else round(score, 1),
        "sample": len(rows),
        "daily_bullish_pct": None if daily_pct is None else round(daily_pct, 1),
        "weekly_bullish_pct": None if weekly_pct is None else round(weekly_pct, 1),
        "positive_ret5_pct": None if positive_ret5_pct is None else round(positive_ret5_pct, 1),
        "healthy_momentum_pct": None if healthy_pct is None else round(healthy_pct, 1),
        "avg_ret5_pct": (
            None if not ret5_values else round(sum(ret5_values) / len(ret5_values), 2)
        ),
    }


def _breadth_snapshot(engine):
    try:
        rows = engine.supabase_request(
            "GET",
            "hanz_swing_signal_monitor"
            "?select=ticker,sector,daily_trend,weekly_trend,risk_validation,updated_at"
            "&limit=500",
        ) or []
    except Exception as exc:
        return {
            "available": False,
            "reason": f"Monitor breadth unavailable: {exc}",
            "market": _bucket_score([]),
            "sectors": {},
        }

    rows = [r for r in rows if _fresh_enough(r.get("updated_at"))]
    market = _bucket_score(rows)

    grouped = {}
    for row in rows:
        sector = str(row.get("sector") or "").strip()
        if not sector:
            continue
        grouped.setdefault(sector, []).append(row)

    sectors = {name: _bucket_score(items) for name, items in grouped.items()}
    return {
        "available": bool(rows),
        "reason": "Completed-bar monitor breadth snapshot.",
        "market": market,
        "sectors": sectors,
    }


def install(engine):
    original_market_regime = engine.market_regime_context
    original_liquidity = engine.liquidity_validation
    original_validation = engine.real_money_validation

    def quality_liquidity_validation(daily):
        out = dict(original_liquidity(daily) or {})
        avg_value = _num(out.get("avg_value20"))
        median_value = _num(out.get("median_value20"))
        reasons = [str(out.get("reason") or "").strip()]
        score = int(out.get("score") or 0)
        passed = bool(out.get("pass"))

        consistency = None
        if avg_value not in (None, 0) and median_value is not None:
            consistency = median_value / avg_value

        if median_value is None or median_value < MIN_MEDIAN_DAILY_VALUE_IDR:
            passed = False
            score -= 30
            reasons.append(
                f"20d median traded value below Rp{MIN_MEDIAN_DAILY_VALUE_IDR:,.0f}."
            )
        else:
            reasons.append(f"20d median traded value Rp{median_value:,.0f}.")

        if consistency is None:
            score -= 5
            reasons.append("Liquidity consistency unavailable.")
        elif consistency < MIN_LIQUIDITY_CONSISTENCY:
            passed = False
            score -= 25
            reasons.append(
                f"Median/average consistency {consistency:.2f}x below "
                f"{MIN_LIQUIDITY_CONSISTENCY:.2f}x."
            )
        elif consistency < LIQUIDITY_CAUTION_CONSISTENCY:
            score -= 10
            reasons.append(
                f"Liquidity consistency only {consistency:.2f}x; average is spike-sensitive."
            )
        else:
            reasons.append(f"Liquidity consistency {consistency:.2f}x.")

        score = max(0, min(100, score))
        if not passed:
            grade = "FAIL"
        elif score >= 90:
            grade = "A"
        elif score >= 75:
            grade = "B"
        else:
            grade = "C"

        out.update({
            "pass": passed,
            "grade": grade,
            "score": score,
            "median_value20": median_value,
            "consistency_ratio": None if consistency is None else round(consistency, 3),
            "median_minimum_idr": MIN_MEDIAN_DAILY_VALUE_IDR,
            "reason": " ".join(x for x in reasons if x),
        })
        return out

    def breadth_aware_market_regime():
        base = dict(original_market_regime() or {})
        breadth = _breadth_snapshot(engine)
        market_breadth = breadth.get("market") or {}
        breadth_score = _num(market_breadth.get("score"))
        base_score = _num(base.get("score"), 0.0)
        base_regime = str(base.get("regime") or "UNKNOWN").upper()

        base["breadth_available"] = bool(breadth.get("available"))
        base["breadth_reason"] = breadth.get("reason")
        base["breadth_score"] = breadth_score
        base["breadth_sample"] = market_breadth.get("sample")
        base["breadth_daily_bullish_pct"] = market_breadth.get("daily_bullish_pct")
        base["breadth_weekly_bullish_pct"] = market_breadth.get("weekly_bullish_pct")
        base["breadth_positive_ret5_pct"] = market_breadth.get("positive_ret5_pct")
        base["breadth_healthy_momentum_pct"] = market_breadth.get("healthy_momentum_pct")
        base["sector_breadth"] = breadth.get("sectors") or {}

        if breadth_score is None or base_regime == "UNKNOWN":
            return base

        blended = round(base_score * 0.65 + breadth_score * 0.35, 1)
        base["index_only_score"] = base_score
        base["score"] = blended

        if base_regime == "RED" or breadth_score < 25:
            base["regime"] = "RED"
            base["size_multiplier"] = 0.0
            base["reason"] = (
                f"{base.get('reason','')} Breadth {breadth_score:.1f}/100 confirms a weak market; "
                "new real-money BUY blocked."
            ).strip()
        elif base_regime == "GREEN" and breadth_score >= 50 and blended >= 72:
            base["regime"] = "GREEN"
            base["size_multiplier"] = 1.0
            base["reason"] = (
                f"{base.get('reason','')} Breadth {breadth_score:.1f}/100 confirms broad participation."
            ).strip()
        else:
            base["regime"] = "YELLOW"
            base["size_multiplier"] = 0.35 if breadth_score < 40 else 0.50
            base["reason"] = (
                f"{base.get('reason','')} Breadth {breadth_score:.1f}/100 is not strong enough "
                "for full-size risk."
            ).strip()

        return base

    def context_validation(ticker, daily, result, levels, fundamental, context):
        rv = dict(original_validation(ticker, daily, result, levels, fundamental, context) or {})
        context = context or {}
        market = context.get("market") or {}

        liq = quality_liquidity_validation(daily)
        rv["liquidity_quality_score"] = liq.get("score")
        rv["liquidity_consistency_ratio"] = liq.get("consistency_ratio")
        rv["liquidity_median_minimum_idr"] = liq.get("median_minimum_idr")
        rv["liquidity_reason"] = liq.get("reason")

        rv["market_breadth_score"] = market.get("breadth_score")
        rv["market_breadth_sample"] = market.get("breadth_sample")
        rv["market_breadth_daily_bullish_pct"] = market.get("breadth_daily_bullish_pct")
        rv["market_breadth_weekly_bullish_pct"] = market.get("breadth_weekly_bullish_pct")
        rv["market_breadth_positive_ret5_pct"] = market.get("breadth_positive_ret5_pct")
        rv["market_breadth_healthy_momentum_pct"] = market.get("breadth_healthy_momentum_pct")

        sector = str((fundamental or {}).get("sector") or "").strip()
        sector_map = market.get("sector_breadth") or {}
        sector_stats = sector_map.get(sector) if sector else None

        sector_score = _num((sector_stats or {}).get("score"))
        sector_sample = int((sector_stats or {}).get("sample") or 0)
        sector_avg_ret5 = _num((sector_stats or {}).get("avg_ret5_pct"))
        stock_ret5 = _num(rv.get("ret5_pct"))
        relative_strength = None
        if stock_ret5 is not None and sector_avg_ret5 is not None:
            relative_strength = stock_ret5 - sector_avg_ret5

        if not sector or sector_score is None or sector_sample < SECTOR_MIN_SAMPLE:
            sector_regime = "UNKNOWN"
            sector_reason = "Sector breadth unavailable or sample too small; no invented penalty."
        elif sector_score >= SECTOR_STRONG_SCORE:
            sector_regime = "STRONG"
            sector_reason = f"Sector breadth {sector_score:.1f}/100 across {sector_sample} names."
            rv["score"] = min(100, int(rv.get("score") or 0) + 5)
        elif sector_score < SECTOR_WEAK_SCORE:
            rs_override = relative_strength is not None and relative_strength >= SECTOR_RS_OVERRIDE_PCT
            if sector_score < SECTOR_BLOCK_SCORE and not rs_override:
                sector_regime = "VERY_WEAK"
                sector_reason = (
                    f"Sector breadth only {sector_score:.1f}/100 across {sector_sample} names; "
                    "stock lacks sufficient relative-strength override."
                )
                if result.get("state") in getattr(engine, "BUY_STATES", {"SWING_BUY"}):
                    rv["gate"] = "BLOCKED"
                    rv["actionable"] = False
                    blockers = list(rv.get("blockers") or [])
                    if "SECTOR_REGIME" not in blockers:
                        blockers.append("SECTOR_REGIME")
                    rv["blockers"] = blockers
                    rv["score"] = max(0, int(rv.get("score") or 0) - 30)
            else:
                sector_regime = "WEAK_RS_OVERRIDE" if rs_override else "WEAK"
                sector_reason = (
                    f"Sector breadth {sector_score:.1f}/100; "
                    + (
                        f"stock outperforms sector by {relative_strength:+.1f}pp, reduced-risk override."
                        if rs_override else "reduced-risk only."
                    )
                )
                cautions = list(rv.get("cautions") or [])
                if "SECTOR_WEAK" not in cautions:
                    cautions.append("SECTOR_WEAK")
                rv["cautions"] = cautions
                if rv.get("gate") == "ELIGIBLE":
                    rv["gate"] = "CAUTION"
                rv["score"] = max(0, int(rv.get("score") or 0) - (5 if rs_override else 12))
                lots = rv.get("suggested_lots")
                if isinstance(lots, int) and lots > 1:
                    rv["suggested_lots"] = max(1, lots // 2)
                    rv["suggested_shares"] = rv["suggested_lots"] * 100
                    entry = _num(levels.get("entry_price") or daily.get("price"))
                    if entry is not None:
                        rv["suggested_position_idr"] = rv["suggested_shares"] * entry
        else:
            sector_regime = "NEUTRAL"
            sector_reason = f"Sector breadth {sector_score:.1f}/100 across {sector_sample} names."

        rv.update({
            "sector": sector or None,
            "sector_regime": sector_regime,
            "sector_score": sector_score,
            "sector_sample": sector_sample,
            "sector_daily_bullish_pct": (sector_stats or {}).get("daily_bullish_pct"),
            "sector_weekly_bullish_pct": (sector_stats or {}).get("weekly_bullish_pct"),
            "sector_positive_ret5_pct": (sector_stats or {}).get("positive_ret5_pct"),
            "sector_avg_ret5_pct": sector_avg_ret5,
            "sector_relative_strength_pp": None if relative_strength is None else round(relative_strength, 2),
            "sector_reason": sector_reason,
        })
        return rv

    engine.liquidity_validation = quality_liquidity_validation
    engine.market_regime_context = breadth_aware_market_regime
    engine.real_money_validation = context_validation

    print(
        "HANZ CONTEXT QUALITY installed | liquidity=MEDIAN+CONSISTENCY | "
        "market=IHSG+BREADTH | sector=BREADTH+RELATIVE_STRENGTH",
        flush=True,
    )
