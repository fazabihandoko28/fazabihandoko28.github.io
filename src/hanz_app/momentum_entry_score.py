"""HANZ single-score momentum entry model.

The ONLY purpose of this score is to answer:
    "How attractive is this stock for a fresh entry now?"

A high score must not mean merely "strong trend". The model deliberately
rewards early/improving momentum, usable entry location and remaining upside,
then penalizes extension, chasing and exhaustion/TP-risk conditions.

This is a deterministic research model and should be calibrated with IDX
out-of-sample / walk-forward evidence before being treated as validated edge.
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


def momentum_entry_score(result, risk_validation):
    """Return one 0-100 HANZ Momentum Entry Score.

    Weighting:
      25  early momentum
      20  volume build-up
      20  entry location
      15  upside remaining / risk-reward
      10  market support
      10  price-action/trigger quality

    Penalties are applied to the same single score. There is no secondary
    setup-quality score exposed to the dashboard.
    """
    result = result or {}
    rv = risk_validation or {}

    def n(key, default=None):
        return _num(rv.get(key), default)

    setup_family = str(
        result.get("setup_family") or rv.get("setup_family") or "NONE"
    ).upper()
    gate = str(rv.get("gate") or "MONITOR").upper()
    momentum_guard = rv.get("momentum_guard") or {}

    # Genuine broken/non-tradable conditions remain zero.
    if momentum_guard.get("blocked"):
        return 0
    if str(rv.get("volatility_status") or "").upper() == "EXTREME":
        return 0
    zero_vol = n("zero_volume_days20", 0) or 0
    avg_value20 = n("avg_value20")
    if zero_vol >= 5:
        return 0
    if avg_value20 is not None and avg_value20 < 100_000_000:
        return 0

    # ---------------------------------------------------------
    # 1) EARLY MOMENTUM — 25
    # Peak score is given to IMPROVING momentum, not mature/extended momentum.
    # ---------------------------------------------------------
    momentum = 0.0
    rsi = n("daily_rsi")
    rsi_change = n("rsi_change_5d")
    ema_slope = n("ema20_slope_5d_pct")
    ret3 = n("ret3_pct")
    ret5 = n("ret5_pct")

    if rsi is not None:
        if 48 <= rsi <= 62:
            momentum += 8
        elif 43 <= rsi < 48 or 62 < rsi <= 68:
            momentum += 5
        elif 68 < rsi <= 72:
            momentum += 2

    if rsi_change is not None:
        if 3 <= rsi_change <= 9:
            momentum += 7
        elif 1 <= rsi_change < 3:
            momentum += 4
        elif rsi_change > 9:
            momentum += 3

    if ema_slope is not None:
        if 0.05 <= ema_slope <= 0.80:
            momentum += 6
        elif -0.20 <= ema_slope < 0.05:
            momentum += 3
        elif 0.80 < ema_slope <= 1.50:
            momentum += 3

    # Mild positive returns are preferred to already-exploded moves.
    if ret3 is not None and ret5 is not None:
        if -1.0 <= ret3 <= 3.5 and -1.0 <= ret5 <= 6.0:
            momentum += 4
        elif ret3 <= 5.0 and ret5 <= 8.0:
            momentum += 2

    momentum = _clamp(momentum, 0.0, 25.0)

    # ---------------------------------------------------------
    # 2) VOLUME BUILD-UP — 20
    # Reward accumulation/expansion; do NOT reward volume climax.
    # ---------------------------------------------------------
    volume = 0.0
    rvol = n("daily_rvol")
    vol_accel = n("volume_accel_5d")

    if rvol is not None:
        if 1.05 <= rvol <= 1.80:
            volume += 11
        elif 0.85 <= rvol < 1.05:
            volume += 7
        elif 1.80 < rvol <= 2.50:
            volume += 6
        elif 0.65 <= rvol < 0.85:
            volume += 3

    if vol_accel is not None:
        if 1.10 <= vol_accel <= 1.80:
            volume += 9
        elif 0.95 <= vol_accel < 1.10:
            volume += 5
        elif 1.80 < vol_accel <= 2.80:
            volume += 4

    volume = _clamp(volume, 0.0, 20.0)

    # ---------------------------------------------------------
    # 3) ENTRY LOCATION — 20
    # Highest near support/trigger BEFORE price has run away.
    # ---------------------------------------------------------
    location = 0.0
    support_atr = n("support_distance_atr")
    breakout_dist = n("breakout_distance_pct")
    entry_status = str(rv.get("entry_status") or "").upper()

    if support_atr is not None:
        if support_atr <= 0.45:
            location += 8
        elif support_atr <= 0.80:
            location += 6
        elif support_atr <= 1.20:
            location += 3

    if breakout_dist is not None:
        # Positive = still below trigger; small negative = freshly through it.
        if 0.0 <= breakout_dist <= 2.5:
            location += 8
        elif -1.5 <= breakout_dist < 0.0:
            location += 7
        elif 2.5 < breakout_dist <= 5.0:
            location += 4
        elif -3.0 <= breakout_dist < -1.5:
            location += 3

    if entry_status == "ENTRY_ZONE":
        location += 4
    elif entry_status == "WAIT_PULLBACK":
        location -= 5

    location = _clamp(location, 0.0, 20.0)

    # ---------------------------------------------------------
    # 4) UPSIDE REMAINING / R:R — 15
    # ---------------------------------------------------------
    upside = 0.0
    rr1 = n("rr_target_1")
    rr2 = n("rr_target_2")
    rr_candidates = [x for x in (rr1, rr2) if x is not None]
    if rr_candidates:
        rr = max(rr_candidates)
        if rr >= 3.0:
            upside = 15
        elif rr >= 2.5:
            upside = 13
        elif rr >= 2.0:
            upside = 10
        elif rr >= 1.7:
            upside = 7
        elif rr >= 1.4:
            upside = 4
        elif rr >= 1.2:
            upside = 2

    # ---------------------------------------------------------
    # 5) MARKET SUPPORT — 10
    # ---------------------------------------------------------
    market = 0.0
    regime = str(rv.get("market_regime") or "").upper()
    market_score = n("market_score")
    if regime == "GREEN":
        market += 8
    elif regime == "YELLOW":
        market += 5
    elif regime == "RED":
        market += 0
    if market_score is not None:
        if market_score >= 90:
            market += 2
        elif market_score >= 75:
            market += 1
    market = _clamp(market, 0.0, 10.0)

    # ---------------------------------------------------------
    # 6) PRICE-ACTION / TRIGGER QUALITY — 10
    # Uses existing engine evidence; does not create a second visible score.
    # ---------------------------------------------------------
    price_action = 0.0
    if bool(rv.get("trigger_confirmed")) or bool(result.get("trigger_confirmed")):
        price_action += 5
    if setup_family == "EARLY_REVERSAL":
        price_action += 3
        if bool(result.get("minor_structure_break")):
            price_action += 2
        elif bool(result.get("higher_low")):
            price_action += 1
    elif setup_family == "PULLBACK_RETEST":
        price_action += 3
    elif setup_family == "BREAKOUT":
        # Fresh breakout can be valid, but it is not automatically better
        # than an earlier entry location.
        price_action += 2
    price_action = _clamp(price_action, 0.0, 10.0)

    # ---------------------------------------------------------
    # EXHAUSTION / TP-RISK PENALTIES
    # These are the critical difference from the old "stronger = higher" rank.
    # ---------------------------------------------------------
    penalty = 0.0

    if ret3 is not None:
        if ret3 >= 10:
            penalty += 16
        elif ret3 >= 7:
            penalty += 11
        elif ret3 >= 5:
            penalty += 6

    if ret5 is not None:
        if ret5 >= 15:
            penalty += 18
        elif ret5 >= 11:
            penalty += 12
        elif ret5 >= 8:
            penalty += 7

    if rsi is not None:
        if rsi >= 80:
            penalty += 14
        elif rsi >= 75:
            penalty += 9
        elif rsi >= 72:
            penalty += 5

    if rvol is not None:
        if rvol >= 4.0:
            penalty += 10
        elif rvol >= 3.0:
            penalty += 6
        elif rvol >= 2.5:
            penalty += 3

    if vol_accel is not None:
        if vol_accel >= 4.0:
            penalty += 8
        elif vol_accel >= 3.0:
            penalty += 4

    # Negative breakout distance means price is already above the trigger.
    if breakout_dist is not None:
        if breakout_dist <= -7:
            penalty += 18
        elif breakout_dist <= -5:
            penalty += 12
        elif breakout_dist <= -3:
            penalty += 7

    if entry_status == "WAIT_PULLBACK":
        penalty += 8
    if bool(rv.get("do_not_chase")):
        penalty += 14
    if momentum_guard.get("caution"):
        penalty += 6
    if bool(momentum_guard.get("failed_breakout")):
        penalty += 15

    # Keep execution/research state from masquerading as timing quality.
    # Only a tiny penalty is used; the score remains an entry-timing measure.
    if gate in {"RESEARCH_ONLY", "PAPER_ONLY"}:
        penalty += 1

    total = momentum + volume + location + upside + market + price_action - penalty
    total = int(_clamp(round(total), 0, 100))

    # Reuse the existing diagnostics field so no dashboard/schema change is needed.
    rv["opportunity_score_breakdown"] = {
        "early_momentum": round(momentum, 1),
        "volume_build_up": round(volume, 1),
        "entry_location": round(location, 1),
        "upside_remaining": round(upside, 1),
        "market_support": round(market, 1),
        "price_action": round(price_action, 1),
        "exhaustion_penalty": round(penalty, 1),
        "setup_family": setup_family,
        "gate": gate,
        "version": "MES1_2026_09_09_SINGLE_ENTRY_SCORE",
    }
    return total
