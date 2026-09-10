"""HANZ early momentum trigger overlay.

Promotes a developing recovery into EARLY_CONFIRMED_BUY when price breaks a
minor 3-bar pivot with real volume, a constructive close, improving structure,
and limited extension. This is deliberately earlier than a mature 20-day
breakout, but still requires measurable confirmation.
"""


def _f(v, default=None):
    try:
        if v is None:
            return default
        return float(v)
    except (TypeError, ValueError):
        return default


def install(engine):
    """Install the early trigger around the engine's existing swing_score."""
    if getattr(engine.swing_score, "_hanz_early_trigger_v2", False):
        return

    original = engine.swing_score

    def wrapped(daily, weekly):
        out = original(daily, weekly)
        daily = daily or {}
        out = dict(out or {})

        price = _f(daily.get("price"))
        prior_high3 = _f(daily.get("prior_high3"))
        last_low = _f(daily.get("last_swing_low"))
        prev_low = _f(daily.get("prev_swing_low"))
        ema20 = _f(daily.get("ema20"))
        atr = _f(daily.get("atr14"))
        rvol = _f(daily.get("rvol20"))
        close_loc = _f(daily.get("close_location"))
        ret1 = _f(daily.get("ret1_pct"))
        ret3 = _f(daily.get("ret3_pct"))
        ret5 = _f(daily.get("ret5_pct"))
        structure = str(daily.get("structure_state") or "UNKNOWN").upper()

        minor_break = bool(
            price is not None and prior_high3 not in (None, 0)
            and price > prior_high3
            and ((price / prior_high3 - 1.0) * 100.0) <= 3.0
        )
        higher_low = bool(
            last_low is not None and prev_low is not None and last_low > prev_low
        )
        structure_improving = higher_low or structure in {"MIXED", "BULLISH_HH_HL"}
        volume_confirm = rvol is not None and rvol >= 1.20
        close_confirm = close_loc is None or close_loc >= 0.58
        positive_bar = ret1 is None or ret1 >= 0
        not_extended = (
            (ret3 is None or ret3 <= 5.0)
            and (ret5 is None or ret5 <= 8.0)
        )
        location_ok = True
        if price is not None and ema20 is not None and atr not in (None, 0):
            location_ok = (price - ema20) <= 1.75 * atr

        early_confirmed = all([
            minor_break,
            structure_improving,
            volume_confirm,
            close_confirm,
            positive_bar,
            not_extended,
            location_ok,
        ])

        if early_confirmed:
            evidence = list(out.get("evidence") or [])
            evidence += [
                "EARLY MOMENTUM V2: minor 3-bar pivot broken before mature breakout",
                f"volume confirmation RVOL {rvol:.2f}x",
                "constructive close + improving swing structure",
                "entry still within measured non-extended zone",
            ]
            out.update({
                "state": "EARLY_CONFIRMED_BUY",
                "setup_family": "EARLY_REVERSAL",
                "minor_structure_break": True,
                "higher_low": higher_low,
                "trigger_confirmed": True,
                "volume_confirm": True,
                "hard_buy_gate": True,
                "raw_buy_gate": True,
                "early_buy_gate": True,
                "evidence": evidence,
            })

        return out

    wrapped._hanz_early_trigger_v2 = True
    engine.swing_score = wrapped
