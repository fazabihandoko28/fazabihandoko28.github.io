"""Regression checks: FAST health must never certify stale or future-dated candles."""
from datetime import timedelta
from unittest.mock import patch

from hanz_app import fast_trading_engine as engine


def test_fast_health_rejects_future_ticker_even_when_oldest_is_valid():
    now = engine.utc_now()
    with patch.object(engine, "_CYCLE_MARKET_BARS", {
        "VALID.JK": now - timedelta(seconds=20),
        "FUTURE.JK": now + timedelta(minutes=5),
    }), patch.object(engine, "_provider_cycle_status", return_value="FRESH"), patch.object(
        engine, "_provider_cycle_error", return_value=None
    ), patch.object(engine, "update_fast_health", side_effect=lambda **kw: kw):
        result = engine.publish_cycle_health()
    assert result["data_status"] == "STALE"
    assert "future-dated" in result["error"]


def test_fast_health_rejects_oldest_stale_ticker():
    now = engine.utc_now()
    with patch.object(engine, "_CYCLE_MARKET_BARS", {
        "FRESH.JK": now - timedelta(seconds=20),
        "STALE.JK": now - timedelta(seconds=engine.MAX_DATA_AGE_SECONDS + 120),
    }), patch.object(engine, "_provider_cycle_status", return_value="FRESH"), patch.object(
        engine, "_provider_cycle_error", return_value=None
    ), patch.object(engine, "update_fast_health", side_effect=lambda **kw: kw):
        result = engine.publish_cycle_health()
    assert result["data_status"] == "STALE"


def test_fast_health_accepts_fresh_bars_with_healthy_provider():
    now = engine.utc_now()
    with patch.object(engine, "_CYCLE_MARKET_BARS", {
        "A.JK": now - timedelta(seconds=20),
        "B.JK": now - timedelta(seconds=30),
    }), patch.object(engine, "_provider_cycle_status", return_value="FRESH"), patch.object(
        engine, "_provider_cycle_error", return_value=None
    ), patch.object(engine, "update_fast_health", side_effect=lambda **kw: kw):
        result = engine.publish_cycle_health()
    assert result["data_status"] == "FRESH"
    assert result["symbols_monitored"] == 2
