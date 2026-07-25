from __future__ import annotations

from math import sqrt
from statistics import fmean
from typing import Sequence


def sma(values: Sequence[float], period: int) -> float | None:
    if period <= 0 or len(values) < period:
        return None
    return fmean(values[-period:])


def ema_series(values: Sequence[float], period: int) -> list[float]:
    if period <= 0 or len(values) < period:
        return []
    seed = fmean(values[:period])
    result = [seed]
    multiplier = 2.0 / (period + 1.0)
    for value in values[period:]:
        result.append((value - result[-1]) * multiplier + result[-1])
    return result


def ema(values: Sequence[float], period: int) -> float | None:
    result = ema_series(values, period)
    return result[-1] if result else None


def rsi(values: Sequence[float], period: int = 14) -> float | None:
    if len(values) < period + 1:
        return None
    gains: list[float] = []
    losses: list[float] = []
    for left, right in zip(values[-period - 1 : -1], values[-period:]):
        change = right - left
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))
    avg_gain = fmean(gains)
    avg_loss = fmean(losses)
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def atr(highs: Sequence[float], lows: Sequence[float], closes: Sequence[float], period: int = 14) -> float | None:
    if len(closes) < period + 1 or len(highs) != len(closes) or len(lows) != len(closes):
        return None
    true_ranges: list[float] = []
    for index in range(len(closes) - period, len(closes)):
        previous_close = closes[index - 1]
        true_ranges.append(max(highs[index] - lows[index], abs(highs[index] - previous_close), abs(lows[index] - previous_close)))
    return fmean(true_ranges)


def relative_volume(volumes: Sequence[float], period: int = 20) -> float | None:
    if len(volumes) < period + 1:
        return None
    baseline = fmean(volumes[-period - 1 : -1])
    if baseline <= 0:
        return None
    return volumes[-1] / baseline


def rolling_high(values: Sequence[float], period: int = 20, *, exclude_latest: bool = True) -> float | None:
    required = period + (1 if exclude_latest else 0)
    if len(values) < required:
        return None
    window = values[-period - 1 : -1] if exclude_latest else values[-period:]
    return max(window)


def rolling_low(values: Sequence[float], period: int = 20, *, exclude_latest: bool = True) -> float | None:
    required = period + (1 if exclude_latest else 0)
    if len(values) < required:
        return None
    window = values[-period - 1 : -1] if exclude_latest else values[-period:]
    return min(window)


def realized_volatility(values: Sequence[float], period: int = 20) -> float | None:
    if len(values) < period + 1:
        return None
    returns = [(values[i] / values[i - 1]) - 1.0 for i in range(len(values) - period, len(values)) if values[i - 1] != 0]
    if len(returns) < 2:
        return None
    mean = fmean(returns)
    variance = sum((item - mean) ** 2 for item in returns) / (len(returns) - 1)
    return sqrt(variance)
