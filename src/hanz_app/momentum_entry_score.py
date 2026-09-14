"""HANZ single-score fresh-entry model.

One question only:
    "How attractive is this stock for a FRESH entry right now?"

Core doctrine (V6):
- Top opportunities should be EARLY, not late/chasing.
- A confirmed bounce/reclaim from support is preferred.
- A stock stalled immediately below resistance is NOT an opportunity until the
  breakout is confirmed (or it first resets/retests into a clean entry).
- AVOID / DO_NOT_CHASE / TP_RISK / RESISTANCE_WAIT can never masquerade as a
  Top-5 opportunity merely because their historical trend is strong.
"""


def _num(value, default=None):
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _clamp(value, lo, hi):
    return max(lo, min(hi, value))


def _set_decision(rv, action, reason, confidence=None):
    rv["hanz_action"] = action
    rv["hanz_action_reason"] = reason
    if confidence is not None:
        rv["hanz_action_confidence"] = int(_clamp(confidence, 0, 100))


def momentum_entry_score(result, risk_validation):
    result = result or {}
    rv = risk_validation or {}

    def n(key, default=None):
        return _num(rv.get(key), default)

    setup_family = str(result.get("setup_family") or rv.get("setup_family") or "NONE").upper()
    gate = str(rv.get("gate") or "MONITOR").upper()
    momentum_guard = rv.get("momentum_guard") or {}
    data_quality = rv.get("data_quality") or {}

    # Support-bounce intelligence may arrive from the predictive intraday result.
    bounce_state = str(
        result.get("support_bounce_state")
        or rv.get("support_bounce_state")
        or "NO_BOUNCE"
    ).upper()
    bounce_recovery = _num(
        result.get("bounce_recovery_pct"),
        _num(rv.get("bounce_recovery_pct")),
    )
    bounce_close_location = _num(
        result.get("intraday_close_location"),
        _num(rv.get("intraday_close_location")),
    )
    bounce_confirmed = bounce_state == "BOUNCE_CONFIRMED"
    bounce_watch = bounce_state == "BOUNCE_WATCH"

    # Persist the classification in risk_validation so the dashboard can filter
    # the same doctrine used by the backend ranking.
    rv["support_bounce_state"] = bounce_state
    if bounce_recovery is not None:
        rv["bounce_recovery_pct"] = bounce_recovery
    if bounce_close_location is not None:
        rv["intraday_close_location"] = bounce_close_location

    # Hard safety/data blocks.
    if data_quality.get("block") or str(rv.get("data_quality_status") or "").upper() == "MISMATCH":
        _set_decision(rv, "AVOID", "Market-data mismatch: BUY is blocked until price data agrees.", 99)
        return 0
    if momentum_guard.get("blocked"):
        _set_decision(rv, "AVOID", "Momentum structure is broken / hard-blocked.", 95)
        return 0
    if str(rv.get("volatility_status") or "").upper() == "EXTREME":
        _set_decision(rv, "AVOID", "Extreme volatility: entry quality is not reliable enough.", 95)
        return 0
    zero_vol = n("zero_volume_days20", 0) or 0
    avg_value20 = n("avg_value20")
    if zero_vol >= 5:
        _set_decision(rv, "AVOID", "Too many zero-volume sessions.", 95)
        return 0
    if avg_value20 is not None and avg_value20 < 100_000_000:
        _set_decision(rv, "AVOID", "Liquidity is below HANZ minimum tradability threshold.", 95)
        return 0

    rsi = n("daily_rsi")
    rsi_change = n("rsi_change_5d")
    ema_slope = n("ema20_slope_5d_pct")
    ret3 = n("ret3_pct")
    ret5 = n("ret5_pct")
    rvol = n("daily_rvol")
    vol_accel = n("volume_accel_5d")
    support_atr = n("support_distance_atr")
    breakout_dist = n("breakout_distance_pct")
    rr1 = n("rr_target_1")
    rr2 = n("rr_target_2")
    rr_candidates = [x for x in (rr1, rr2) if x is not None]
    rr = max(rr_candidates) if rr_candidates else None
    entry_status = str(rv.get("entry_status") or "").upper()
    regime = str(rv.get("market_regime") or "").upper()
    market_score = n("market_score")

    trigger_confirmed = bool(rv.get("trigger_confirmed")) or bool(result.get("trigger_confirmed"))
    minor_break = bool(result.get("minor_structure_break")) or bool(rv.get("minor_structure_break"))
    higher_low = bool(result.get("higher_low")) or bool(rv.get("higher_low"))
    volume_confirm = bool(rv.get("volume_confirm")) or bool(result.get("volume_confirm"))

    # IMPORTANT: positive breakout_dist = price is still BELOW breakout trigger.
    # If it is sitting within 1.25% below resistance and has NOT broken it, that
    # is a resistance-capped setup. It must not occupy Top-5 fresh opportunities.
    resistance_capped = bool(
        breakout_dist is not None
        and 0.0 <= breakout_dist <= 1.25
        and not trigger_confirmed
        and not bounce_confirmed
    )
    rv["resistance_capped"] = resistance_capped

    # 1) Early momentum — 22
    momentum = 0.0
    if rsi is not None:
        if 48 <= rsi <= 62: momentum += 7
        elif 43 <= rsi < 48 or 62 < rsi <= 68: momentum += 4
        elif 68 < rsi <= 72: momentum += 1
    if rsi_change is not None:
        if 3 <= rsi_change <= 9: momentum += 6
        elif 1 <= rsi_change < 3: momentum += 3
        elif rsi_change > 9: momentum += 2
    if ema_slope is not None:
        if 0.05 <= ema_slope <= 0.80: momentum += 5
        elif -0.20 <= ema_slope < 0.05: momentum += 2
        elif 0.80 < ema_slope <= 1.50: momentum += 2
    if ret3 is not None and ret5 is not None:
        if -1.0 <= ret3 <= 3.5 and -1.0 <= ret5 <= 6.0: momentum += 4
        elif ret3 <= 5.0 and ret5 <= 8.0: momentum += 2
    momentum = _clamp(momentum, 0, 22)

    # 2) Volume build-up — 18
    volume = 0.0
    if rvol is not None:
        if 1.20 <= rvol <= 1.80: volume += 10
        elif 1.05 <= rvol < 1.20: volume += 6
        elif 0.85 <= rvol < 1.05: volume += 2
        elif 1.80 < rvol <= 2.50: volume += 5
    if vol_accel is not None:
        if 1.10 <= vol_accel <= 1.80: volume += 8
        elif 0.95 <= vol_accel < 1.10: volume += 3
        elif 1.80 < vol_accel <= 2.80: volume += 3
    volume = _clamp(volume, 0, 18)

    # 3) Entry location — 18. Support proximity matters more than 'almost breakout'.
    location = 0.0
    if support_atr is not None:
        if support_atr <= 0.45: location += 10
        elif support_atr <= 0.80: location += 7
        elif support_atr <= 1.20: location += 3
    if breakout_dist is not None:
        # Confirmed breakout/retest may receive location credit. Sitting just below
        # resistance does NOT receive the old +8 reward anymore.
        if trigger_confirmed and -1.0 <= breakout_dist <= 0.5: location += 5
        elif trigger_confirmed and -1.5 <= breakout_dist < -1.0: location += 3
        elif 1.25 < breakout_dist <= 3.0: location += 2
    if entry_status == "ENTRY_ZONE": location += 3
    elif entry_status == "WAIT_PULLBACK": location -= 5
    location = _clamp(location, 0, 18)

    # 4) Fresh support-bounce quality — 22 (new primary early-entry factor).
    bounce = 0.0
    if bounce_confirmed:
        bounce += 14
        if bounce_recovery is not None:
            if 0.8 <= bounce_recovery <= 4.0: bounce += 4
            elif bounce_recovery > 4.0: bounce += 2
        if bounce_close_location is not None:
            if bounce_close_location >= 0.70: bounce += 4
            elif bounce_close_location >= 0.60: bounce += 2
    elif bounce_watch:
        bounce += 5
    bounce = _clamp(bounce, 0, 22)

    # 5) Remaining upside / R:R — 12
    upside = 0.0
    if rr is not None:
        if rr >= 3.0: upside = 12
        elif rr >= 2.5: upside = 10
        elif rr >= 2.0: upside = 8
        elif rr >= 1.7: upside = 4
        elif rr >= 1.4: upside = 2

    # 6) Market support — 8
    market = 0.0
    if regime == "GREEN": market += 6
    elif regime == "YELLOW": market += 3
    if market_score is not None:
        if market_score >= 90: market += 2
        elif market_score >= 75: market += 1
    market = _clamp(market, 0, 8)

    # Price action — up to 8 bonus, but not enough to overwhelm poor location.
    price_action = 0.0
    if trigger_confirmed: price_action += 4
    if volume_confirm: price_action += 2
    if minor_break: price_action += 1
    if higher_low: price_action += 1
    price_action = _clamp(price_action, 0, 8)

    penalty = 0.0
    if resistance_capped:
        penalty += 30
    if not trigger_confirmed and not bounce_confirmed:
        penalty += 6
    if not volume_confirm:
        if rvol is None or rvol < 1.05: penalty += 8
        elif rvol < 1.20: penalty += 4
    if breakout_dist is not None and breakout_dist > 3.0:
        penalty += 3
    if support_atr is not None and support_atr > 1.20:
        penalty += 6
    if rr is not None and rr < 1.7:
        penalty += 8

    # Exhaustion / chase penalties.
    if ret3 is not None:
        if ret3 >= 10: penalty += 16
        elif ret3 >= 7: penalty += 11
        elif ret3 >= 5: penalty += 6
    if ret5 is not None:
        if ret5 >= 15: penalty += 18
        elif ret5 >= 11: penalty += 12
        elif ret5 >= 8: penalty += 7
    if rsi is not None:
        if rsi >= 80: penalty += 14
        elif rsi >= 75: penalty += 9
        elif rsi >= 72: penalty += 5
    if rvol is not None:
        if rvol >= 4.0: penalty += 10
        elif rvol >= 3.0: penalty += 6
        elif rvol >= 2.5: penalty += 3
    if vol_accel is not None:
        if vol_accel >= 4.0: penalty += 8
        elif vol_accel >= 3.0: penalty += 4
    if breakout_dist is not None:
        if breakout_dist <= -7: penalty += 18
        elif breakout_dist <= -5: penalty += 12
        elif breakout_dist <= -3: penalty += 7
    if entry_status == "WAIT_PULLBACK": penalty += 8
    if bool(rv.get("do_not_chase")): penalty += 14
    if momentum_guard.get("caution"): penalty += 6
    if bool(momentum_guard.get("failed_breakout")): penalty += 18
    if gate in {"RESEARCH_ONLY", "PAPER_ONLY"}: penalty += 2

    raw_total = int(_clamp(round(momentum + volume + location + bounce + upside + market + price_action - penalty), 0, 100))

    extended = bool(rv.get("do_not_chase")) or (breakout_dist is not None and breakout_dist <= -3.0)
    exhaustion = (
        (ret3 is not None and ret3 >= 7.0)
        or (ret5 is not None and ret5 >= 11.0)
        or (rsi is not None and rsi >= 75.0)
    )

    rr_ok = rr is not None and rr >= 2.0
    location_ok = entry_status != "WAIT_PULLBACK" and not extended and (support_atr is None or support_atr <= 1.20)
    market_ok = regime != "RED"
    trigger_ok = trigger_confirmed
    volume_ok = volume_confirm or (rvol is not None and 1.20 <= rvol <= 2.50)
    breakout_ok = breakout_dist is None or (-1.5 <= breakout_dist <= 1.5)

    # Explicit non-opportunity states first.
    if resistance_capped:
        action = "RESISTANCE_WAIT"
        reason = "Price is stalled immediately below resistance; wait for a confirmed breakout/retest or a reset to support."
        total = min(raw_total, 39)
    elif extended:
        action = "DO_NOT_CHASE"
        reason = "Price is too extended from the usable trigger; wait for a retest/pullback."
        total = min(raw_total, 49)
    elif exhaustion and penalty >= 15:
        action = "TP_RISK"
        reason = "Momentum is mature and fresh-entry reward has deteriorated; profit-taking risk is elevated."
        total = min(raw_total, 49)
    elif raw_total >= 75 and trigger_ok and volume_ok and rr_ok and location_ok and market_ok and breakout_ok:
        action = "BUY"
        reason = "Confirmed trigger, volume, clean location and >=2.0 R:R are aligned for a fresh swing entry."
        total = raw_total
    elif bounce_confirmed and raw_total >= 58 and location_ok and market_ok:
        action = "WAIT_TRIGGER"
        missing = []
        if not trigger_ok: missing.append("trigger confirmation")
        if not volume_ok: missing.append("volume confirmation")
        if not rr_ok: missing.append("R:R >=2.0")
        reason = "Fresh support bounce is confirmed"
        if missing:
            reason += "; waiting for " + ", ".join(missing)
        reason += "."
        total = min(raw_total, 74)
    elif raw_total >= 55 and location_ok and market_ok and not resistance_capped:
        action = "WAIT"
        missing = []
        if not trigger_ok: missing.append("confirmed trigger")
        if not volume_ok: missing.append("volume >=1.20x / volume confirmation")
        if not rr_ok: missing.append("R:R >=2.0")
        reason = "Setup is developing but not yet a fresh-entry candidate"
        if missing: reason += "; waiting for " + ", ".join(missing)
        reason += "."
        total = min(raw_total, 69)
    else:
        action = "AVOID"
        reason = "Current timing, momentum, location and risk/reward are not good enough for a fresh entry."
        total = min(raw_total, 49)

    _set_decision(
        rv,
        action,
        reason,
        total if action in {"BUY", "WAIT_TRIGGER", "WAIT"} else max(70, 100 - total),
    )

    rv["opportunity_score_breakdown"] = {
        "early_momentum": round(momentum, 1),
        "volume_build_up": round(volume, 1),
        "entry_location": round(location, 1),
        "support_bounce": round(bounce, 1),
        "upside_remaining": round(upside, 1),
        "market_support": round(market, 1),
        "price_action": round(price_action, 1),
        "penalty": round(penalty, 1),
        "raw_score_before_action_cap": raw_total,
        "setup_family": setup_family,
        "gate": gate,
        "resistance_capped": resistance_capped,
        "support_bounce_state": bounce_state,
        "version": "MES6_2026_09_14_FRESH_BOUNCE_FIRST",
    }
    return total
