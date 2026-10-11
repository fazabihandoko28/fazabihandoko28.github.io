"""HANZ V12 final data/feed integrity gate.

Runs after the existing market_data_router so it can validate the exact candle
used by the strategy, not merely the provider's latest raw snapshot.
"""

from __future__ import annotations


def _num(value):
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _bar_date(daily):
    text = str((daily or {}).get("bar_at") or "")
    return text[:10] or None


def install(engine):
    original_validation = engine.real_money_validation

    def integrity_validation(ticker, daily, result, levels, fundamental, context):
        rv = dict(original_validation(ticker, daily, result, levels, fundamental, context) or {})
        dq = dict(rv.get("data_quality") or {})
        blockers = list(rv.get("blockers") or [])
        cautions = list(rv.get("cautions") or [])

        strategy_date = _bar_date(daily)
        verifier_date = str(dq.get("verifier_date") or "")[:10] or None
        primary_date = str(dq.get("primary_date") or "")[:10] or None

        expected_date = None
        try:
            expected = engine.latest_completed_idx_date()
            expected_date = expected.isoformat() if expected else None
        except Exception:
            expected_date = None

        state = str((result or {}).get("state") or "").upper()
        is_buy_state = state in getattr(engine, "BUY_STATES", {"SWING_BUY"})

        o = _num((daily or {}).get("open"))
        h = _num((daily or {}).get("high"))
        l = _num((daily or {}).get("low"))
        c = _num((daily or {}).get("price"))

        sane = (
            None not in (o, h, l, c)
            and min(o, h, l, c) > 0
            and h >= max(o, c, l)
            and l <= min(o, c, h)
            and h >= l
        )

        integrity_status = "OK"
        reasons = []
        hard_block = False

        if not sane:
            integrity_status = "INVALID_OHLC"
            reasons.append("Strategy candle failed OHLC sanity checks.")
            hard_block = True

        if is_buy_state and expected_date and strategy_date and strategy_date != expected_date:
            integrity_status = "STALE_STRATEGY_BAR"
            reasons.append(
                f"Strategy bar {strategy_date} is not latest completed IDX session {expected_date}."
            )
            hard_block = True

        if verifier_date and strategy_date and verifier_date != strategy_date:
            integrity_status = "VERIFIER_DATE_MISMATCH"
            reasons.append(
                f"Independent verifier date {verifier_date} differs from strategy bar {strategy_date}."
            )
            hard_block = True

        router_status = str(dq.get("status") or "UNVERIFIED").upper()
        router_block = bool(dq.get("block"))
        if router_block:
            hard_block = True
            if integrity_status == "OK":
                integrity_status = router_status or "PROVIDER_MISMATCH"
            reasons.append(str(dq.get("reason") or "Provider cross-check blocked the data."))

        if hard_block:
            rv["gate"] = "BLOCKED"
            rv["actionable"] = False
            if "DATA_INTEGRITY" not in blockers:
                blockers.append("DATA_INTEGRITY")
            confidence = 0
        else:
            if router_status == "VERIFIED":
                confidence = 100
            elif router_status == "VERIFIED_PRICE_VOLUME_CAUTION":
                confidence = 85
            elif router_status in {"UNVERIFIED", "DISABLED", "UNKNOWN"}:
                confidence = 65
                if "DATA_SINGLE_SOURCE" not in cautions:
                    cautions.append("DATA_SINGLE_SOURCE")
                reasons.append("Independent same-session verifier unavailable; single-source confidence only.")
            else:
                confidence = 75

            if bool(dq.get("fallback_used")):
                confidence = max(0, confidence - 5)
                reasons.append("Primary provider fallback was used.")

        rv["blockers"] = blockers
        rv["cautions"] = cautions
        rv["data_integrity_status"] = integrity_status
        rv["data_confidence_score"] = int(confidence)
        rv["data_strategy_bar_date"] = strategy_date
        rv["data_expected_completed_date"] = expected_date
        rv["data_router_primary_date"] = primary_date
        rv["data_verifier_date"] = verifier_date
        rv["data_same_session_verified"] = bool(
            verifier_date and strategy_date and verifier_date == strategy_date and not hard_block
        )
        rv["data_integrity_reason"] = " ".join(reasons) if reasons else "Strategy candle/session integrity checks passed."

        return rv

    engine.real_money_validation = integrity_validation
    print(
        "HANZ DATA INTEGRITY V12 installed | OHLC_SANITY + LATEST_COMPLETED_BAR + SAME_SESSION_VERIFY",
        flush=True,
    )
