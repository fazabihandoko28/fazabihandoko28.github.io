"""HANZ single-score momentum entry model.

Purpose: answer one question only:
    "How attractive is this stock for a fresh entry right now?"

Important invariant:
- 75+ is reserved for an actually actionable BUY-quality setup.
- WAIT / DO_NOT_CHASE / TP_RISK / AVOID may never keep a BUY-like score.
This prevents a merely strong-looking stock from ranking above a cleaner entry.
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

    # Hard safety/data blocks.
    if data_quality.get("block") or str(rv.get("data_quality_status") or "").upper() == "MISMATCH":
        _set_decision(rv, "AVOID", "Market-data mismatch: real-money BUY is blocked until price data agrees.", 99)
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

    # 1) Early momentum — 25
    momentum = 0.0
    if rsi is not None:
        if 48 <= rsi <= 62: momentum += 8
        elif 43 <= rsi < 48 or 62 < rsi <= 68: momentum += 5
        elif 68 < rsi <= 72: momentum += 2
    if rsi_change is not None:
        if 3 <= rsi_change <= 9: momentum += 7
        elif 1 <= rsi_change < 3: momentum += 4
        elif rsi_change > 9: momentum += 3
    if ema_slope is not None:
        if 0.05 <= ema_slope <= 0.80: momentum += 6
        elif -0.20 <= ema_slope < 0.05: momentum += 3
        elif 0.80 < ema_slope <= 1.50: momentum += 3
    if ret3 is not None and ret5 is not None:
        if -1.0 <= ret3 <= 3.5 and -1.0 <= ret5 <= 6.0: momentum += 4
        elif ret3 <= 5.0 and ret5 <= 8.0: momentum += 2
    momentum = _clamp(momentum, 0, 25)

    # 2) Volume build-up — 20. Weak volume is no longer treated generously.
    volume = 0.0
    if rvol is not None:
        if 1.20 <= rvol <= 1.80: volume += 11
        elif 1.05 <= rvol < 1.20: volume += 7
        elif 0.85 <= rvol < 1.05: volume += 3
        elif 1.80 < rvol <= 2.50: volume += 6
    if vol_accel is not None:
        if 1.10 <= vol_accel <= 1.80: volume += 9
        elif 0.95 <= vol_accel < 1.10: volume += 4
        elif 1.80 < vol_accel <= 2.80: volume += 4
    volume = _clamp(volume, 0, 20)

    # 3) Entry location — 20
    location = 0.0
    if support_atr is not None:
        if support_atr <= 0.45: location += 8
        elif support_atr <= 0.80: location += 6
        elif support_atr <= 1.20: location += 3
    if breakout_dist is not None:
        # Positive = still below trigger; negative = above trigger.
        if -1.0 <= breakout_dist <= 1.0: location += 8
        elif 1.0 < breakout_dist <= 2.0: location += 5
        elif -1.5 <= breakout_dist < -1.0: location += 5
        elif 2.0 < breakout_dist <= 3.0: location += 2
        elif -3.0 <= breakout_dist < -1.5: location += 2
    if entry_status == "ENTRY_ZONE": location += 4
    elif entry_status == "WAIT_PULLBACK": location -= 5
    location = _clamp(location, 0, 20)

    # 4) Remaining upside / R:R — 15
    upside = 0.0
    if rr is not None:
        if rr >= 3.0: upside = 15
        elif rr >= 2.5: upside = 13
        elif rr >= 2.0: upside = 10
        elif rr >= 1.7: upside = 6
        elif rr >= 1.4: upside = 3

    # 5) Market support — 10
    market = 0.0
    if regime == "GREEN": market += 8
    elif regime == "YELLOW": market += 4
    if market_score is not None:
        if market_score >= 90: market += 2
        elif market_score >= 75: market += 1
    market = _clamp(market, 0, 10)

    # 6) Price-action quality — 10. Confirmed trigger matters more than setup label.
    price_action = 0.0
    if trigger_confirmed: price_action += 6
    if volume_confirm: price_action += 2
    if minor_break: price_action += 1
    if higher_low: price_action += 1
    price_action = _clamp(price_action, 0, 10)

    penalty = 0.0
    # Immature / unconfirmed-entry penalties.
    if not trigger_confirmed:
        penalty += 8
    if not volume_confirm:
        if rvol is None or rvol < 1.05: penalty += 9
        elif rvol < 1.20: penalty += 5
    if breakout_dist is not None and breakout_dist > 1.5:
        penalty += 6
    if support_atr is not None and support_atr > 1.20:
        penalty += 5
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

    raw_total = int(_clamp(round(momentum + volume + location + upside + market + price_action - penalty), 0, 100))

    extended = bool(rv.get("do_not_chase")) or (breakout_dist is not None and breakout_dist <= -3.0)
    exhaustion = ((ret3 is not None and ret3 >= 7.0) or (ret5 is not None and ret5 >= 11.0) or (rsi is not None and rsi >= 75.0))

    # BUY is intentionally strict. Early structure alone is not enough.
    rr_ok = rr is not None and rr >= 2.0
    location_ok = entry_status != "WAIT_PULLBACK" and not extended and (support_atr is None or support_atr <= 1.20)
    market_ok = regime != "RED"
    trigger_ok = trigger_confirmed
    volume_ok = volume_confirm or (rvol is not None and 1.20 <= rvol <= 2.50)
    breakout_ok = breakout_dist is None or (-1.5 <= breakout_dist <= 1.5)

    if extended:
        action = "DO_NOT_CHASE"
        reason = "Price is too extended from the usable trigger; wait for a retest/pullback."
        total = min(raw_total, 59)
    elif exhaustion and penalty >= 15:
        action = "TP_RISK"
        reason = "Momentum is mature and fresh-entry reward has deteriorated; profit-taking risk is elevated."
        total = min(raw_total, 59)
    elif raw_total >= 75 and trigger_ok and volume_ok and rr_ok and location_ok and market_ok and breakout_ok:
        action = "BUY"
        reason = "Confirmed trigger, volume, entry location and >=2.0 R:R are aligned for a fresh swing entry."
        total = raw_total
    elif raw_total >= 55 and location_ok and market_ok:
        action = "WAIT"
        missing = []
        if not trigger_ok: missing.append("confirmed trigger")
        if not volume_ok: missing.append("volume >=1.20x / volume confirmation")
        if not rr_ok: missing.append("R:R >=2.0")
        if not breakout_ok: missing.append("clean trigger distance")
        reason = "Setup is not ready for real-money entry"
        if missing: reason += "; waiting for " + ", ".join(missing)
        reason += "."
        total = min(raw_total, 74)
    else:
        action = "AVOID"
        reason = "Current timing, momentum, location and risk/reward are not good enough for a fresh entry."
        total = min(raw_total, 49)

    _set_decision(rv, action, reason, total if action in {"BUY", "WAIT"} else max(70, 100 - total))

    rv["opportunity_score_breakdown"] = {
        "early_momentum": round(momentum, 1),
        "volume_build_up": round(volume, 1),
        "entry_location": round(location, 1),
        "upside_remaining": round(upside, 1),
        "market_support": round(market, 1),
        "price_action": round(price_action, 1),
        "penalty": round(penalty, 1),
        "raw_score_before_action_cap": raw_total,
        "setup_family": setup_family,
        "gate": gate,
        "version": "MES5_2026_09_11_STRICT_TIMING",
    }
    return total
