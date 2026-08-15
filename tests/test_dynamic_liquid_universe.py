import pandas as pd
from hanz_app.build_liquid_universe import evaluate


def frame(volumes, closes=None):
    closes = closes or [100 + (i % 7) for i in range(len(volumes))]
    return pd.DataFrame({"Close": closes, "Volume": volumes})


def row(symbol="TEST"):
    return {"symbol": symbol, "yahoo_ticker": symbol + ".JK", "sector": "Test"}


def test_liquid_moving_share_is_eligible():
    m = evaluate(row(), frame([20_000_000] * 60), 60)
    assert m.eligible
    assert m.active_ratio == 1.0


def test_zero_volume_sleeping_share_is_rejected():
    volumes = [0] * 30 + [20_000_000] * 30
    m = evaluate(row(), frame(volumes), 60)
    assert not m.eligible
    assert "TOO_MANY_ZERO_VOLUME_DAYS" in m.rejection_reason


def test_static_share_is_rejected_even_with_volume():
    m = evaluate(row(), frame([20_000_000] * 60, [100] * 60), 60)
    assert not m.eligible
    assert "TOO_STATIC" in m.rejection_reason
