from hanz_app.swing_entry_runner import actionable_top5_score


def base_rv():
    return {
        "avg_value20": 5_000_000_000,
        "zero_volume_days20": 0,
        "daily_rsi": 55,
        "rsi_change_5d": 4,
        "ema20_slope_5d_pct": 0.25,
        "ret3_pct": 1.5,
        "ret5_pct": 3.0,
        "daily_rvol": 1.4,
        "volume_accel_5d": 1.3,
        "support_distance_atr": 0.5,
        "rr_target_1": 2.2,
        "rr_target_2": 2.8,
        "entry_status": "ENTRY_ZONE",
        "market_regime": "GREEN",
        "market_score": 85,
        "volatility_status": "NORMAL",
        "momentum_guard": {},
        "data_quality": {},
    }


def test_avoid_never_enters_top5():
    rv = base_rv()
    # Remove the qualities required for an actionable candidate.
    rv.update({
        "daily_rsi": 30,
        "daily_rvol": 0.5,
        "volume_accel_5d": 0.5,
        "support_distance_atr": 2.0,
        "rr_target_1": 1.0,
        "rr_target_2": 1.1,
        "market_regime": "RED",
    })
    score = actionable_top5_score({}, rv)
    assert score == 0
    assert rv["hanz_action"] == "AVOID"
    assert rv["top5_excluded"] is True


def test_unconfirmed_stock_stalled_under_resistance_is_excluded():
    rv = base_rv()
    rv.update({
        "breakout_distance_pct": 0.5,
        "trigger_confirmed": False,
        "volume_confirm": True,
    })
    score = actionable_top5_score({"setup_family": "BREAKOUT"}, rv)
    assert score == 0
    assert rv["hanz_action"] == "RESISTANCE_WAIT"
    assert rv["resistance_capped"] is True
    assert rv["top5_excluded"] is True


def test_confirmed_support_bounce_can_rank_as_wait_trigger():
    rv = base_rv()
    rv.update({
        "breakout_distance_pct": 2.0,
        "trigger_confirmed": False,
        "volume_confirm": True,
    })
    result = {
        "support_bounce_state": "BOUNCE_CONFIRMED",
        "bounce_recovery_pct": 1.5,
        "intraday_close_location": 0.78,
        "higher_low": True,
        "minor_structure_break": True,
    }
    score = actionable_top5_score(result, rv)
    assert score > 0
    assert rv["hanz_action"] == "WAIT_TRIGGER"
    assert rv["top5_excluded"] is False
