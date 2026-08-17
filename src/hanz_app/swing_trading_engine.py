
import json
import math
import os
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf

# Firebase Admin is optional. Alerts continue writing to Supabase even
# when the GitHub Actions Firebase secret is not configured.
try:
    import firebase_admin
    from firebase_admin import credentials, messaging
except Exception:
    firebase_admin = None
    credentials = None
    messaging = None



# ============================================================
# HANZ SWING / WEEKLY TRADING ENGINE
# Separate from Fast Engine. Do NOT replace fast_trading_engine.py
# ============================================================

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_SECRET_KEY = os.getenv("SUPABASE_SECRET_KEY", "")

SWING_INTERVAL = int(
    os.getenv("HANZ_SWING_INTERVAL", "1800")
)
RUN_ONCE = os.getenv(
    "HANZ_SWING_RUN_ONCE", "0"
) == "1"

DAILY_INTERVAL = os.getenv(
    "HANZ_SWING_DAILY_TIMEFRAME", "1d"
)
DAILY_PERIOD = os.getenv(
    "HANZ_SWING_DAILY_PERIOD", "1y"
)

WEEKLY_INTERVAL = os.getenv(
    "HANZ_SWING_WEEKLY_TIMEFRAME", "1wk"
)
WEEKLY_PERIOD = os.getenv(
    "HANZ_SWING_WEEKLY_PERIOD", "2y"
)

MIN_WATCH_SCORE = int(
    os.getenv("HANZ_SWING_MIN_WATCH_SCORE", "6")
)
MIN_CONFIRM_SCORE = int(
    os.getenv("HANZ_SWING_MIN_CONFIRM_SCORE", "7")
)
MIN_BUY_SCORE = int(
    os.getenv("HANZ_SWING_MIN_BUY_SCORE", "8")
)

MAX_SYMBOLS_PER_CYCLE = int(
    os.getenv("HANZ_SWING_MAX_SYMBOLS_PER_CYCLE", "220")
)


# Discount Intelligence V1
# Analyst-target calls are deliberately limited to stronger setups
# so the 200-stock scan does not hammer Yahoo analysis endpoints.
DISCOUNT_ANALYST_STATES = {
    "SWING_CONFIRMING",
    "SWING_BUY",
}
DISCOUNT_ANALYST_DELAY_SECONDS = float(
    os.getenv("HANZ_SWING_ANALYST_DELAY_SECONDS", "0.25")
)


# Fundamental Intelligence is fetched only for stronger setups.
# This keeps the 200-stock final scan reasonable while enriching
# SWING_CONFIRMING and SWING_BUY candidates.
FUNDAMENTAL_STATES = {
    "SWING_CONFIRMING",
    "SWING_BUY",
}
FUNDAMENTAL_FETCH_DELAY_SECONDS = float(
    os.getenv("HANZ_SWING_FUNDAMENTAL_DELAY_SECONDS", "0.25")
)


JAKARTA_TZ = ZoneInfo("Asia/Jakarta")

TRAILING_ATR_MULTIPLIER_T1 = float(
    os.getenv("HANZ_SWING_TRAILING_ATR_T1", "1.5")
)
TRAILING_ATR_MULTIPLIER_T2 = float(
    os.getenv("HANZ_SWING_TRAILING_ATR_T2", "1.0")
)

FIREBASE_SERVICE_ACCOUNT_JSON = os.getenv(
    "FIREBASE_SERVICE_ACCOUNT_JSON", ""
).strip()

PUSH_DASHBOARD_URL = os.getenv(
    "HANZ_SWING_DASHBOARD_URL",
    "https://fazabihandoko28.github.io/dashboard/swing/",
)

# Push remains intentionally quiet. TARGET_1/TARGET_2 are stored as
# dashboard alerts but do not create push notifications.
PUSH_ALERT_TYPES = {
    "STOP_LOSS",
    "TRAILING_ACTIVATED",
    "PROTECT_PROFIT",
    "CONFIRMED_SELL",
}

_FIREBASE_APP = None



# ============================================================
# IDX / BEI TRADING CALENDAR GATE
# Time zone: Asia/Jakarta (WIB)
#
# 2026 holidays follow the published IDX 2026 trading-holiday
# calendar (Peng-00171/BEI.POP/09-2025). The environment variable
# HANZ_IDX_HOLIDAYS_JSON can override/extend this map without code
# changes, e.g. {"2026-12-31":"Trading Holiday"}.
# ============================================================

IDX_HOLIDAYS_2026 = {
    "2026-01-01": "New Year 2026",
    "2026-01-16": "Isra Mikraj",
    "2026-02-16": "Chinese New Year Collective Leave",
    "2026-02-17": "Chinese New Year",
    "2026-03-18": "Nyepi Collective Leave",
    "2026-03-19": "Nyepi",
    "2026-03-20": "Eid al-Fitr Collective Leave",
    "2026-03-23": "Eid al-Fitr Collective Leave",
    "2026-03-24": "Eid al-Fitr Collective Leave",
    "2026-04-03": "Good Friday",
    "2026-05-01": "Labour Day",
    "2026-05-14": "Ascension Day",
    "2026-05-15": "Ascension Day Collective Leave",
    "2026-05-27": "Eid al-Adha",
    "2026-05-28": "Eid al-Adha Collective Leave",
    "2026-06-01": "Pancasila Day",
    "2026-06-16": "Islamic New Year",
    "2026-08-17": "Independence Day",
    "2026-08-25": "Prophet Muhammad's Birthday",
    "2026-12-24": "Christmas Collective Leave",
    "2026-12-25": "Christmas Day",
    "2026-12-31": "IDX Trading Holiday",
}

IDX_HOLIDAYS = dict(IDX_HOLIDAYS_2026)

try:
    extra_holidays = json.loads(
        os.getenv("HANZ_IDX_HOLIDAYS_JSON", "{}")
    )
    if isinstance(extra_holidays, dict):
        IDX_HOLIDAYS.update(
            {
                str(k): str(v)
                for k, v in extra_holidays.items()
            }
        )
except Exception as exc:
    print(
        f"IDX calendar override ignored: {exc}",
        flush=True,
    )


def jakarta_now():
    return utc_now().astimezone(JAKARTA_TZ)


def idx_trading_day(date_obj):
    if date_obj.weekday() >= 5:
        return False, "Weekend"

    key = date_obj.isoformat()
    if key in IDX_HOLIDAYS:
        return False, IDX_HOLIDAYS[key]

    # Fail-safe: the embedded official calendar is verified for 2026.
    # For another year, require explicit holiday data rather than
    # pretending every weekday is a trading day.
    if date_obj.year != 2026:
        return False, "IDX calendar year not verified"

    return True, "Trading Day"


def idx_market_session(now=None):
    now = now or jakarta_now()
    trading_day, reason = idx_trading_day(now.date())

    if not trading_day:
        state = (
            "CLOSED_WEEKEND"
            if now.weekday() >= 5
            else "CLOSED_HOLIDAY"
        )
        if reason == "IDX calendar year not verified":
            state = "CALENDAR_UNVERIFIED"

        return {
            "state": state,
            "reason": reason,
            "is_trading_day": False,
            "allow_portfolio_monitor": False,
            "allow_final_scan": False,
            "now_wib": now.isoformat(),
        }

    minutes = now.hour * 60 + now.minute
    friday = now.weekday() == 4

    session_1_end = 11 * 60 + 30 if friday else 12 * 60
    session_2_start = 14 * 60 if friday else 13 * 60 + 30

    if minutes < 8 * 60 + 45:
        state = "CLOSED_BEFORE_HOURS"
    elif minutes < 9 * 60:
        state = "PRE_OPEN"
    elif minutes < session_1_end:
        state = "SESSION_1"
    elif minutes < session_2_start:
        state = "LUNCH_BREAK"
    elif minutes < 15 * 60 + 50:
        state = "SESSION_2"
    elif minutes <= 16 * 60 + 15:
        state = "POST_CLOSE"
    else:
        state = "CLOSED_AFTER_HOURS"

    # Portfolio monitoring is useful during active trading and lunch.
    allow_portfolio_monitor = state in {
        "SESSION_1",
        "LUNCH_BREAK",
        "SESSION_2",
        "POST_CLOSE",
    }

    # Swing candidate generation only uses the completed daily bar.
    allow_final_scan = state == "POST_CLOSE"

    return {
        "state": state,
        "reason": "Trading Day",
        "is_trading_day": True,
        "allow_portfolio_monitor": allow_portfolio_monitor,
        "allow_final_scan": allow_final_scan,
        "now_wib": now.isoformat(),
    }


def previous_idx_trading_day(date_obj):
    candidate = date_obj
    for _ in range(370):
        candidate = candidate.fromordinal(
            candidate.toordinal() - 1
        )
        ok, _ = idx_trading_day(candidate)
        if ok:
            return candidate
    return None


def next_idx_trading_day(date_obj):
    candidate = date_obj
    for _ in range(370):
        candidate = candidate.fromordinal(
            candidate.toordinal() + 1
        )
        ok, _ = idx_trading_day(candidate)
        if ok:
            return candidate
    return None

def utc_now():
    return datetime.now(timezone.utc)


def now_iso():
    return utc_now().isoformat()


def normalize_ticker(ticker):
    ticker = str(ticker or "").strip().upper()
    if not ticker:
        return None
    if not ticker.endswith(".JK"):
        ticker += ".JK"
    return ticker


def clean_ticker(ticker):
    return str(ticker or "").upper().replace(".JK", "")


def safe_float(value):
    try:
        if value is None:
            return None
        x = float(value)
        if math.isnan(x):
            return None
        return x
    except Exception:
        return None


def safe_bool(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def values_different(a, b, tolerance=1e-9):
    if a is None and b is None:
        return False
    if a is None or b is None:
        return True
    try:
        return abs(float(a) - float(b)) > tolerance
    except Exception:
        return a != b


def supabase_request(method, path, payload=None, prefer=None):
    if not SUPABASE_URL or not SUPABASE_SECRET_KEY:
        raise RuntimeError(
            "SUPABASE_URL / SUPABASE_SECRET_KEY missing"
        )

    url = f"{SUPABASE_URL}/rest/v1/{path}"

    headers = {
        "apikey": SUPABASE_SECRET_KEY,
        "Authorization": f"Bearer {SUPABASE_SECRET_KEY}",
        "Content-Type": "application/json",
    }

    if prefer:
        headers["Prefer"] = prefer

    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")

    req = urllib.request.Request(
        url=url,
        data=data,
        headers=headers,
        method=method,
    )

    try:
        with urllib.request.urlopen(
            req, timeout=45
        ) as resp:
            raw = resp.read()
            if not raw:
                return None
            return json.loads(raw.decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(
            "utf-8", errors="replace"
        )
        raise RuntimeError(
            f"HTTP {exc.code}: {body}"
        ) from exc


def download_frame(ticker, interval, period):
    symbol = normalize_ticker(ticker)

    df = yf.download(
        symbol,
        interval=interval,
        period=period,
        auto_adjust=False,
        progress=False,
        threads=False,
    )

    if df is None or df.empty:
        raise RuntimeError("No market data")

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [
            col[0] if isinstance(col, tuple)
            else col
            for col in df.columns
        ]

    df = df.dropna(
        subset=["Open", "High", "Low", "Close"]
    )

    if df.empty:
        raise RuntimeError("No usable bars")

    return df


def rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(
        alpha=1 / period,
        adjust=False,
    ).mean()

    avg_loss = loss.ewm(
        alpha=1 / period,
        adjust=False,
    ).mean()

    rs = avg_gain / avg_loss.replace(0, pd.NA)
    return 100 - (100 / (1 + rs))


def atr(df, period=14):
    prev_close = df["Close"].shift(1)

    tr = pd.concat(
        [
            df["High"] - df["Low"],
            (df["High"] - prev_close).abs(),
            (df["Low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)

    return tr.ewm(
        alpha=1 / period,
        adjust=False,
    ).mean()


def daily_metrics(df):
    if len(df) < 60:
        raise RuntimeError(
            "Insufficient daily history"
        )

    close = df["Close"].astype(float)
    volume = df["Volume"].astype(float)

    ema20 = close.ewm(
        span=20, adjust=False
    ).mean()
    ema50 = close.ewm(
        span=50, adjust=False
    ).mean()

    rsi14 = rsi(close, 14)
    atr14 = atr(df, 14)

    avg_vol20 = volume.rolling(20).mean()

    last = len(df) - 1
    prior_high20 = safe_float(
        df["High"].iloc[
            max(0, last - 20):last
        ].max()
    )
    prior_low20 = safe_float(
        df["Low"].iloc[
            max(0, last - 20):last
        ].min()
    )

    price = safe_float(close.iloc[-1])
    vol = safe_float(volume.iloc[-1])
    avg_vol = safe_float(avg_vol20.iloc[-1])

    rvol = (
        vol / avg_vol
        if (
            vol is not None
            and avg_vol not in (None, 0)
        )
        else None
    )

    ret5 = None
    if len(close) >= 6:
        base = safe_float(close.iloc[-6])
        if base and price:
            ret5 = (
                (price - base)
                / base
                * 100
            )

    lookback_52w = df.iloc[-252:] if len(df) >= 252 else df
    week52_high = safe_float(lookback_52w["High"].max())
    week52_low = safe_float(lookback_52w["Low"].min())

    week52_discount_pct = None
    week52_position_pct = None

    if price is not None and week52_high not in (None, 0):
        week52_discount_pct = (
            (week52_high - price) / week52_high * 100
        )

    if (
        price is not None
        and week52_high is not None
        and week52_low is not None
        and week52_high > week52_low
    ):
        week52_position_pct = (
            (price - week52_low)
            / (week52_high - week52_low)
            * 100
        )

    return {
        "price": price,
        "open": safe_float(df["Open"].iloc[-1]),
        "high": safe_float(df["High"].iloc[-1]),
        "low": safe_float(df["Low"].iloc[-1]),
        "week52_high": week52_high,
        "week52_low": week52_low,
        "week52_discount_pct": safe_float(week52_discount_pct),
        "week52_position_pct": safe_float(week52_position_pct),
        "ema20": safe_float(ema20.iloc[-1]),
        "ema50": safe_float(ema50.iloc[-1]),
        "rsi14": safe_float(rsi14.iloc[-1]),
        "atr14": safe_float(atr14.iloc[-1]),
        "rvol20": safe_float(rvol),
        "prior_high20": prior_high20,
        "prior_low20": prior_low20,
        "ret5_pct": safe_float(ret5),
        "bar_at": pd.Timestamp(
            df.index[-1]
        ).isoformat(),
    }


def weekly_metrics(df):
    if len(df) < 25:
        raise RuntimeError(
            "Insufficient weekly history"
        )

    close = df["Close"].astype(float)

    ema10 = close.ewm(
        span=10, adjust=False
    ).mean()
    ema20 = close.ewm(
        span=20, adjust=False
    ).mean()

    rsi14 = rsi(close, 14)

    return {
        "price": safe_float(close.iloc[-1]),
        "ema10": safe_float(ema10.iloc[-1]),
        "ema20": safe_float(ema20.iloc[-1]),
        "rsi14": safe_float(rsi14.iloc[-1]),
        "bar_at": pd.Timestamp(
            df.index[-1]
        ).isoformat(),
    }


def swing_score(daily, weekly):
    score = 0
    evidence = []

    price = daily["price"]

    daily_trend = (
        daily["ema20"] is not None
        and daily["ema50"] is not None
        and daily["ema20"] > daily["ema50"]
    )

    weekly_trend = (
        weekly["ema10"] is not None
        and weekly["ema20"] is not None
        and weekly["ema10"] > weekly["ema20"]
    )

    breakout = (
        price is not None
        and daily["prior_high20"] is not None
        and price > daily["prior_high20"]
    )

    near_breakout = False
    if (
        price is not None
        and daily["prior_high20"] not in (None, 0)
    ):
        gap = (
            daily["prior_high20"] - price
        ) / daily["prior_high20"] * 100
        near_breakout = 0 <= gap <= 3.0

    if (
        price is not None
        and daily["ema20"] is not None
        and price > daily["ema20"]
    ):
        score += 1
        evidence.append("price above daily EMA20")

    if daily_trend:
        score += 1
        evidence.append("daily EMA20 above EMA50")

    if weekly_trend:
        score += 2
        evidence.append("weekly EMA10 above EMA20")

    rsi_d = daily["rsi14"]
    if rsi_d is not None and 50 <= rsi_d <= 72:
        score += 1
        evidence.append(f"daily RSI {rsi_d:.1f}")

    rsi_w = weekly["rsi14"]
    if rsi_w is not None and 50 <= rsi_w <= 75:
        score += 1
        evidence.append(f"weekly RSI {rsi_w:.1f}")

    rvol = daily["rvol20"] or 0
    if rvol >= 1.2:
        score += 1
        evidence.append(f"daily RVOL {rvol:.2f}x")

    if breakout:
        score += 2
        evidence.append("20-day breakout")
    elif near_breakout:
        score += 1
        evidence.append("within 3% of 20-day breakout")

    ret5 = daily["ret5_pct"]
    if ret5 is not None and ret5 > 0:
        score += 1
        evidence.append(f"5-day momentum +{ret5:.2f}%")

    state = "NO_SETUP"

    if (
        score >= MIN_BUY_SCORE
        and breakout
        and weekly_trend
    ):
        state = "SWING_BUY"
    elif score >= MIN_CONFIRM_SCORE:
        state = "SWING_CONFIRMING"
    elif score >= MIN_WATCH_SCORE:
        state = "SWING_WATCH"

    return {
        "score": min(score, 10),
        "state": state,
        "daily_trend": (
            "BULLISH"
            if daily_trend
            else "NOT_BULLISH"
        ),
        "weekly_trend": (
            "BULLISH"
            if weekly_trend
            else "NOT_BULLISH"
        ),
        "breakout": breakout,
        "evidence": evidence,
    }


def risk_levels(
    daily,
    result=None,
    discount=None,
    fundamental=None,
):
    """Adaptive Swing entry + risk + dynamic take-profit plan.

    Entry:
    - uses completed daily close as reference
    - gives an entry zone, not a fake exact fill
    - avoids chasing excessively far above breakout/EMA20

    Targets:
    - based on actual risk (R), ATR, trend/score quality
    - nearby 52-week high can become a practical resistance target
    - T2 can stretch toward analyst mean only when it is reasonably close
    - after T1 the existing portfolio logic activates ATR trailing, so
      profit protection keeps moving dynamically with the trade.
    """
    price = safe_float(daily.get("price"))
    atr14 = safe_float(daily.get("atr14"))
    prior_low20 = safe_float(daily.get("prior_low20"))
    breakout_level = safe_float(daily.get("prior_high20"))
    ema20 = safe_float(daily.get("ema20"))
    week52_high = safe_float(daily.get("week52_high"))

    result = result or {}
    discount = discount or {}
    fundamental = fundamental or {}

    if (
        price is None
        or atr14 is None
        or atr14 <= 0
    ):
        return {
            "entry_price": None,
            "entry_low": None,
            "entry_high": None,
            "entry_status": "NO_DATA",
            "entry_note": "Insufficient price/ATR data",
            "stop_loss": None,
            "target_1": None,
            "target_2": None,
            "risk_per_share": None,
            "rr_target_1": None,
            "rr_target_2": None,
            "target_mode": None,
        }

    # -------------------------
    # STOP LOSS
    # -------------------------
    atr_stop = price - (2.0 * atr14)

    if prior_low20 is None:
        stop = atr_stop
    else:
        stop = max(
            atr_stop,
            prior_low20,
        )

    if stop >= price:
        stop = atr_stop

    # -------------------------
    # ENTRY ZONE
    # -------------------------
    # Ideal entry is around the confirmed close / breakout retest.
    entry_price = price
    entry_low = price - (0.40 * atr14)
    entry_high = price + (0.25 * atr14)

    if breakout_level is not None:
        # Do not set the lower edge below the confirmed breakout area.
        entry_low = max(
            entry_low,
            breakout_level,
        )

    # Detect an overextended breakout so HANZ can say "wait pullback"
    # instead of encouraging a chase above the ideal swing zone.
    breakout_extension_atr = None
    if breakout_level is not None:
        breakout_extension_atr = (
            (price - breakout_level) / atr14
        )

    ema_extension_pct = None
    if ema20 not in (None, 0):
        ema_extension_pct = (
            (price - ema20) / ema20 * 100
        )

    if (
        (
            breakout_extension_atr is not None
            and breakout_extension_atr > 1.25
        )
        or (
            ema_extension_pct is not None
            and ema_extension_pct > 10
        )
    ):
        entry_status = "WAIT_PULLBACK"
        entry_price = max(
            breakout_level or (price - 0.75 * atr14),
            price - 0.75 * atr14,
        )
        entry_low = max(
            breakout_level or (entry_price - 0.25 * atr14),
            entry_price - 0.25 * atr14,
        )
        entry_high = entry_price + (0.25 * atr14)
        entry_note = (
            "SWING BUY confirmed, but price is extended. "
            "Prefer pullback into the entry zone; do not chase."
        )
    else:
        entry_status = "ENTRY_ZONE"
        entry_note = (
            "SWING BUY confirmed. Use the entry zone on the next "
            "trading session and avoid buying above the upper band."
        )

    # Risk is calculated from ideal/reference entry, not blindly from close.
    risk = entry_price - stop

    if risk <= 0:
        stop = entry_price - (2.0 * atr14)
        risk = entry_price - stop

    # -------------------------
    # DYNAMIC TARGET STRENGTH
    # -------------------------
    swing_score = safe_float(result.get("score")) or 0
    fundamental_score = safe_float(
        fundamental.get("fundamental_score")
    )
    discount_score = safe_float(
        discount.get("discount_score")
    )

    strength = 0

    if swing_score >= 9:
        strength += 2
    elif swing_score >= 8:
        strength += 1

    if result.get("weekly_trend") == "BULLISH":
        strength += 1

    if (
        fundamental_score is not None
        and fundamental_score >= 75
    ):
        strength += 1

    if (
        discount_score is not None
        and discount_score >= 70
    ):
        strength += 1

    # Stronger setups are allowed more room to run.
    if strength >= 5:
        t1_r = 2.0
        t2_r = 4.0
        target_mode = "STRONG_TREND"
    elif strength >= 3:
        t1_r = 1.8
        t2_r = 3.2
        target_mode = "QUALITY_TREND"
    else:
        t1_r = 1.5
        t2_r = 2.5
        target_mode = "STANDARD_SWING"

    t1 = entry_price + (t1_r * risk)
    t2 = entry_price + (t2_r * risk)

    # -------------------------
    # RESISTANCE-AWARE TARGETS
    # -------------------------
    # If 52W high is a realistic nearby resistance, use it rather than
    # blindly placing T1 beyond an obvious supply zone.
    if (
        week52_high is not None
        and week52_high > entry_price
    ):
        resistance_r = (
            (week52_high - entry_price) / risk
        )

        if 1.0 <= resistance_r <= (t1_r + 0.6):
            t1 = week52_high
            target_mode += "+52W_RESISTANCE"

        elif (
            resistance_r > t1_r
            and resistance_r <= (t2_r + 0.8)
        ):
            t2 = week52_high
            target_mode += "+52W_RESISTANCE"

    # Analyst mean is not treated as a guaranteed target.
    # It may extend T2 only if reasonably close to the technical target.
    analyst_target = safe_float(
        discount.get("analyst_target_mean")
    )

    if (
        analyst_target is not None
        and analyst_target > entry_price
        and analyst_target > t2
    ):
        analyst_r = (
            (analyst_target - entry_price) / risk
        )

        if analyst_r <= (t2_r + 1.0):
            t2 = analyst_target
            target_mode += "+ANALYST_CAP"

    # Ensure logical ordering.
    if t1 <= entry_price:
        t1 = entry_price + (1.5 * risk)

    if t2 <= t1:
        t2 = max(
            entry_price + (2.5 * risk),
            t1 + risk,
        )

    rr1 = (
        (t1 - entry_price) / risk
        if risk > 0
        else None
    )
    rr2 = (
        (t2 - entry_price) / risk
        if risk > 0
        else None
    )

    return {
        "entry_price": round(entry_price, 4),
        "entry_low": round(entry_low, 4),
        "entry_high": round(entry_high, 4),
        "entry_status": entry_status,
        "entry_note": entry_note,
        "stop_loss": round(stop, 4),
        "target_1": round(t1, 4),
        "target_2": round(t2, 4),
        "risk_per_share": round(risk, 4),
        "rr_target_1": (
            round(rr1, 2)
            if rr1 is not None
            else None
        ),
        "rr_target_2": (
            round(rr2, 2)
            if rr2 is not None
            else None
        ),
        "target_mode": target_mode,
    }



# ============================================================
# SWING PORTFOLIO / ALERTS
# ============================================================

def fetch_swing_portfolio():
    return supabase_request(
        "GET",
        "hanz_swing_portfolio"
        "?status=eq.OPEN"
        "&select=*"
        "&order=opened_at.asc",
    ) or []


def update_swing_portfolio(portfolio_id, payload):
    if portfolio_id is None or not payload:
        return

    encoded = urllib.parse.quote(
        str(portfolio_id),
        safe="",
    )

    payload = dict(payload)
    payload["updated_at"] = now_iso()

    supabase_request(
        "PATCH",
        f"hanz_swing_portfolio?id=eq.{encoded}",
        payload,
        prefer="return=minimal",
    )


def swing_alert_dedupe_key(
    portfolio_id,
    ticker,
    alert_type,
    *,
    daily=False,
):
    base = (
        f"{portfolio_id}:"
        f"{clean_ticker(ticker)}:"
        f"{alert_type}"
    )

    if daily:
        return (
            base
            + ":"
            + utc_now()
            .astimezone(JAKARTA_TZ)
            .date()
            .isoformat()
        )

    return base


def insert_swing_alert(
    *,
    position,
    alert_type,
    priority,
    message,
    reason=None,
    daily_dedupe=False,
):
    user_id = position.get("user_id")
    portfolio_id = position.get("id")
    ticker = position.get("ticker")

    if not user_id or portfolio_id is None or not ticker:
        return False

    dedupe_key = swing_alert_dedupe_key(
        portfolio_id,
        ticker,
        alert_type,
        daily=daily_dedupe,
    )

    payload = {
        "user_id": user_id,
        "portfolio_id": portfolio_id,
        "ticker": clean_ticker(ticker),
        "alert_type": alert_type,
        "priority": priority,
        "message": message,
        "reason": reason,
        "dedupe_key": dedupe_key,
        "created_at": now_iso(),
    }

    try:
        supabase_request(
            "POST",
            "hanz_swing_alerts",
            payload,
            prefer="return=minimal",
        )

        print(
            f"SWING ALERT: {clean_ticker(ticker)} "
            f"{alert_type} portfolio={portfolio_id}",
            flush=True,
        )

        send_selective_push(
            ticker=ticker,
            alert_type=alert_type,
            title=(
                f"{clean_ticker(ticker)} — "
                f"{alert_type.replace('_', ' ')}"
            ),
            message=message,
            user_id=user_id,
            portfolio_id=portfolio_id,
        )

        return True

    except Exception as exc:
        # Unique dedupe_key suppresses repeat trigger spam.
        if "409" in str(exc):
            return False
        raise


def jakarta_date_string():
    return (
        utc_now()
        .astimezone(JAKARTA_TZ)
        .date()
        .isoformat()
    )


def firebase_app():
    global _FIREBASE_APP

    if _FIREBASE_APP is not None:
        return _FIREBASE_APP

    if firebase_admin is None or credentials is None:
        return None

    if not FIREBASE_SERVICE_ACCOUNT_JSON:
        return None

    try:
        info = json.loads(FIREBASE_SERVICE_ACCOUNT_JSON)
        cred = credentials.Certificate(info)

        try:
            _FIREBASE_APP = firebase_admin.get_app()
        except ValueError:
            _FIREBASE_APP = firebase_admin.initialize_app(cred)

        return _FIREBASE_APP

    except Exception as exc:
        print(
            f"SWING FCM init unavailable: {exc}",
            flush=True,
        )
        return None


def push_event_key(
    *,
    ticker,
    alert_type,
    user_id,
    portfolio_id,
):
    if alert_type == "PROTECT_PROFIT":
        return (
            f"SWING:{user_id}:{portfolio_id}:"
            f"{alert_type}:{jakarta_date_string()}"
        )

    return (
        f"SWING:{user_id}:{portfolio_id}:"
        f"{alert_type}"
    )


def reserve_push_event(
    *,
    event_key,
    ticker,
    alert_type,
    user_id,
    portfolio_id,
):
    payload = {
        "event_key": event_key,
        "user_id": user_id,
        "portfolio_id": portfolio_id,
        "ticker": clean_ticker(ticker),
        "alert_type": alert_type,
        "status": "PENDING",
        "created_at": now_iso(),
    }

    try:
        supabase_request(
            "POST",
            "hanz_push_log",
            payload,
            prefer="return=minimal",
        )
        return True
    except Exception as exc:
        if "409" in str(exc):
            return False
        raise


def finish_push_event(event_key, status, error=None):
    encoded = urllib.parse.quote(
        str(event_key),
        safe="",
    )

    payload = {
        "status": status,
        "updated_at": now_iso(),
    }

    if status == "SENT":
        payload["sent_at"] = now_iso()

    if error:
        payload["last_error"] = str(error)[:1000]

    try:
        supabase_request(
            "PATCH",
            f"hanz_push_log?event_key=eq.{encoded}",
            payload,
            prefer="return=minimal",
        )
    except Exception:
        pass


def release_failed_push_event(event_key):
    encoded = urllib.parse.quote(
        str(event_key),
        safe="",
    )

    try:
        supabase_request(
            "DELETE",
            f"hanz_push_log?event_key=eq.{encoded}",
            prefer="return=minimal",
        )
    except Exception:
        pass


def get_push_installation_ids(user_id):
    encoded_user = urllib.parse.quote(
        str(user_id),
        safe="",
    )

    rows = supabase_request(
        "GET",
        "hanz_push_devices"
        "?enabled=eq.true"
        f"&user_id=eq.{encoded_user}"
        "&select=installation_id",
    ) or []

    ids = []
    seen = set()

    for row in rows:
        installation_id = str(
            row.get("installation_id")
            or ""
        ).strip()

        if (
            installation_id
            and installation_id not in seen
        ):
            seen.add(installation_id)
            ids.append(installation_id)

    return ids


def send_selective_push(
    *,
    ticker,
    alert_type,
    title,
    message,
    user_id,
    portfolio_id,
):
    if alert_type not in PUSH_ALERT_TYPES:
        return

    app = firebase_app()

    if app is None or messaging is None:
        print(
            f"SWING PUSH SKIPPED: Firebase not configured "
            f"({alert_type} {clean_ticker(ticker)})",
            flush=True,
        )
        return

    event_key = push_event_key(
        ticker=ticker,
        alert_type=alert_type,
        user_id=user_id,
        portfolio_id=portfolio_id,
    )

    if not reserve_push_event(
        event_key=event_key,
        ticker=ticker,
        alert_type=alert_type,
        user_id=user_id,
        portfolio_id=portfolio_id,
    ):
        print(
            f"SWING PUSH SUPPRESSED duplicate: {event_key}",
            flush=True,
        )
        return

    try:
        installation_ids = get_push_installation_ids(
            user_id
        )

        if not installation_ids:
            finish_push_event(
                event_key,
                "NO_DEVICE",
            )
            return

        messages = []

        for fid in installation_ids:
            messages.append(
                messaging.Message(
                    data={
                        "title": str(title),
                        "body": str(message),
                        "message": str(message),
                        "ticker": clean_ticker(ticker),
                        "alert_type": str(alert_type),
                        "url": PUSH_DASHBOARD_URL,
                        "portfolio_id": str(portfolio_id),
                        "dedupe_key": event_key,
                    },
                    fid=fid,
                )
            )

        response = messaging.send_each(
            messages,
            app=app,
        )

        finish_push_event(
            event_key,
            "SENT",
        )

        print(
            f"SWING PUSH SENT: {event_key} "
            f"success={response.success_count} "
            f"failed={response.failure_count}",
            flush=True,
        )

    except Exception as exc:
        release_failed_push_event(event_key)

        print(
            f"SWING PUSH FAILED: {event_key} — {exc}",
            flush=True,
        )


def apply_swing_auto_trailing(
    position,
    daily,
):
    """Manage peak/trailing from daily bars.

    Important:
    - Target reach uses today's HIGH.
    - Peak uses today's HIGH.
    - A newly activated trailing stop is NOT allowed to trigger a
      same-day CONFIRMED_SELL because daily OHLC cannot tell whether
      the day's low happened before or after the day's high.
    """
    if not safe_bool(
        position.get("auto_trailing"),
        True,
    ):
        return position, False

    portfolio_id = position.get("id")
    high = safe_float(daily.get("high"))
    atr14 = safe_float(daily.get("atr14"))
    avg_buy = safe_float(position.get("avg_buy"))
    target_1 = safe_float(position.get("target_1"))
    target_2 = safe_float(position.get("target_2"))
    current_peak = safe_float(position.get("peak_price"))
    current_trail = safe_float(position.get("trailing_stop"))
    was_active = safe_bool(
        position.get("trailing_active"),
        False,
    )

    if high is None:
        return position, False

    peak = max(
        value
        for value in [current_peak, high]
        if value is not None
    )

    reached_t1 = (
        target_1 is not None
        and high >= target_1
    )

    reached_t2 = (
        target_2 is not None
        and high >= target_2
    )

    active = was_active or reached_t1

    multiplier = (
        TRAILING_ATR_MULTIPLIER_T2
        if reached_t2
        else TRAILING_ATR_MULTIPLIER_T1
    )

    new_trail = current_trail

    if (
        active
        and atr14 is not None
        and atr14 > 0
    ):
        candidate = peak - multiplier * atr14

        if avg_buy is not None:
            candidate = max(
                candidate,
                avg_buy,
            )

        if current_trail is None:
            new_trail = candidate
        else:
            new_trail = max(
                current_trail,
                candidate,
            )

    updates = {
        "last_price": daily.get("price"),
        "last_monitor_at": now_iso(),
        "last_daily_bar_at": daily.get("bar_at"),
    }

    if values_different(current_peak, peak):
        updates["peak_price"] = peak

    if active != was_active:
        updates["trailing_active"] = active

        if active and not position.get(
            "trailing_activated_at"
        ):
            updates[
                "trailing_activated_at"
            ] = now_iso()

    if (
        active
        and values_different(
            safe_float(
                position.get(
                    "trailing_atr_multiplier"
                )
            ),
            multiplier,
        )
    ):
        updates[
            "trailing_atr_multiplier"
        ] = multiplier

    if (
        active
        and values_different(
            current_trail,
            new_trail,
        )
    ):
        updates["trailing_stop"] = new_trail
        updates[
            "last_trailing_update_at"
        ] = now_iso()

    if reached_t1 and not position.get(
        "target_1_reached_at"
    ):
        updates["target_1_reached_at"] = now_iso()

    if reached_t2 and not position.get(
        "target_2_reached_at"
    ):
        updates["target_2_reached_at"] = now_iso()

    if updates and portfolio_id is not None:
        update_swing_portfolio(
            portfolio_id,
            updates,
        )
        position.update(updates)

    just_activated = (
        active
        and not was_active
    )

    if just_activated:
        insert_swing_alert(
            position=position,
            alert_type="TRAILING_ACTIVATED",
            priority=75,
            message=(
                f"Target 1 reached. "
                f"High {high:.2f}. "
                f"Swing trailing activated at "
                f"{new_trail:.2f} "
                f"({multiplier:.1f}× ATR)."
            ),
            reason="Target 1 activated swing trailing protection.",
        )

    if (
        reached_t1
        and not position.get(
            "_t1_alert_processed"
        )
    ):
        insert_swing_alert(
            position=position,
            alert_type="TARGET_1_REACHED",
            priority=60,
            message=(
                f"Target 1 reached. "
                f"Daily high {high:.2f}."
            ),
            reason="First swing target reached.",
        )
        position["_t1_alert_processed"] = True

    if (
        reached_t2
        and not position.get(
            "_t2_alert_processed"
        )
    ):
        insert_swing_alert(
            position=position,
            alert_type="TARGET_2_REACHED",
            priority=70,
            message=(
                f"Target 2 reached. "
                f"Daily high {high:.2f}."
            ),
            reason="Second swing target reached.",
        )
        position["_t2_alert_processed"] = True

    return position, just_activated


def swing_portfolio_signal(
    position,
    daily,
    weekly,
    *,
    trailing_just_activated=False,
    allow_structural_exit=True,
):
    close = safe_float(daily.get("price"))
    low = safe_float(daily.get("low"))
    high = safe_float(daily.get("high"))

    avg_buy = safe_float(
        position.get("avg_buy")
    )
    stop_loss = safe_float(
        position.get("stop_loss")
    )
    trailing_stop = safe_float(
        position.get("trailing_stop")
    )
    target_1 = safe_float(
        position.get("target_1")
    )
    target_2 = safe_float(
        position.get("target_2")
    )

    trailing_active = safe_bool(
        position.get("trailing_active"),
        False,
    )

    if close is None:
        return {
            "signal": "NO_DATA",
            "priority": 0,
            "reason": "No daily close.",
            "pnl_pct": None,
        }

    pnl_pct = None

    if avg_buy not in (None, 0):
        pnl_pct = (
            close / avg_buy - 1
        ) * 100

    # Highest priority: hard stop breach.
    if (
        stop_loss is not None
        and low is not None
        and low <= stop_loss
    ):
        return {
            "signal": "STOP_LOSS",
            "priority": 100,
            "reason": (
                f"Daily low {low:.2f} "
                f"breached hard stop {stop_loss:.2f}."
            ),
            "pnl_pct": pnl_pct,
        }

    # Trailing breach is actionable only if trailing existed before
    # this daily bar. This avoids false same-day OHLC sequencing.
    if (
        trailing_active
        and not trailing_just_activated
        and trailing_stop is not None
        and low is not None
        and low <= trailing_stop
    ):
        return {
            "signal": "CONFIRMED_SELL",
            "priority": 95,
            "reason": (
                f"Daily low {low:.2f} "
                f"breached swing trailing stop "
                f"{trailing_stop:.2f}."
            ),
            "pnl_pct": pnl_pct,
        }

    daily_breakdown = (
        daily.get("prior_low20") is not None
        and close < daily["prior_low20"]
    )

    daily_bearish = (
        daily.get("ema20") is not None
        and close < daily["ema20"]
    )

    weekly_bearish = (
        weekly.get("ema10") is not None
        and weekly.get("ema20") is not None
        and weekly["ema10"] < weekly["ema20"]
    )

    if (
        allow_structural_exit
        and daily_breakdown
        and daily_bearish
        and weekly_bearish
    ):
        return {
            "signal": "CONFIRMED_SELL",
            "priority": 90,
            "reason": (
                "Daily 20-day breakdown + close below "
                "daily EMA20 + weekly EMA10 below EMA20."
            ),
            "pnl_pct": pnl_pct,
        }

    reached_t1 = (
        target_1 is not None
        and high is not None
        and high >= target_1
    )

    if (
        allow_structural_exit
        and reached_t1
        and pnl_pct is not None
        and pnl_pct > 0
        and (
            daily_bearish
            or (
                daily.get("rsi14") is not None
                and daily["rsi14"] < 50
            )
        )
    ):
        return {
            "signal": "PROTECT_PROFIT",
            "priority": 65,
            "reason": (
                "Position has reached Target 1 but "
                "daily momentum is weakening."
            ),
            "pnl_pct": pnl_pct,
        }

    if (
        target_2 is not None
        and high is not None
        and high >= target_2
    ):
        return {
            "signal": "TARGET_2_REACHED",
            "priority": 50,
            "reason": "Target 2 reached; trailing remains active.",
            "pnl_pct": pnl_pct,
        }

    if reached_t1:
        return {
            "signal": "TARGET_1_REACHED",
            "priority": 40,
            "reason": "Target 1 reached; trailing protection active.",
            "pnl_pct": pnl_pct,
        }

    return {
        "signal": "HOLD",
        "priority": 10,
        "reason": "Swing structure remains valid.",
        "pnl_pct": pnl_pct,
    }


def monitor_swing_portfolio(*, allow_structural_exit=True):
    positions = fetch_swing_portfolio()
    monitored = 0
    errors = 0
    frame_cache = {}

    for position in positions:
        ticker = position.get("ticker")
        portfolio_id = position.get("id")

        if not ticker:
            continue

        try:
            cache_key = clean_ticker(ticker)

            if cache_key not in frame_cache:
                daily_df = download_frame(
                    ticker,
                    DAILY_INTERVAL,
                    DAILY_PERIOD,
                )

                weekly_df = download_frame(
                    ticker,
                    WEEKLY_INTERVAL,
                    WEEKLY_PERIOD,
                )

                frame_cache[cache_key] = (
                    daily_metrics(daily_df),
                    weekly_metrics(weekly_df),
                )

            daily, weekly = frame_cache[cache_key]
            monitored += 1

            position, just_activated = (
                apply_swing_auto_trailing(
                    position,
                    daily,
                )
            )

            result = swing_portfolio_signal(
                position,
                daily,
                weekly,
                trailing_just_activated=just_activated,
                allow_structural_exit=allow_structural_exit,
            )

            signal = result["signal"]

            updates = {
                "signal": signal,
                "last_price": daily.get("price"),
                "last_pnl_pct": result.get("pnl_pct"),
                "last_monitor_at": now_iso(),
                "last_daily_bar_at": daily.get("bar_at"),
                "last_weekly_bar_at": weekly.get("bar_at"),
                "last_signal_reason": result.get("reason"),
            }

            update_swing_portfolio(
                portfolio_id,
                updates,
            )
            position.update(updates)

            if signal in {
                "STOP_LOSS",
                "CONFIRMED_SELL",
            }:
                insert_swing_alert(
                    position=position,
                    alert_type=signal,
                    priority=result["priority"],
                    message=(
                        f"Price {daily['price']:.2f}. "
                        f"{result['reason']}"
                    ),
                    reason=result["reason"],
                )

            elif signal == "PROTECT_PROFIT":
                insert_swing_alert(
                    position=position,
                    alert_type=signal,
                    priority=result["priority"],
                    message=(
                        f"Price {daily['price']:.2f}. "
                        f"{result['reason']}"
                    ),
                    reason=result["reason"],
                    daily_dedupe=True,
                )

            print(
                f"SWING PORTFOLIO {clean_ticker(ticker)} "
                f"portfolio={portfolio_id} "
                f"signal={signal} "
                f"pnl={result.get('pnl_pct')}",
                flush=True,
            )

        except Exception as exc:
            errors += 1
            print(
                f"SWING PORTFOLIO {ticker} failed: {exc}",
                flush=True,
            )

    return {
        "positions": len(positions),
        "monitored": monitored,
        "errors": errors,
    }



def fetch_universe():
    rows = supabase_request(
        "GET",
        "hanz_swing_universe"
        "?enabled=eq.true"
        "&select=ticker,priority"
        "&order=priority.desc,ticker.asc",
    ) or []

    tickers = []

    for row in rows:
        ticker = clean_ticker(
            row.get("ticker")
        )
        if ticker:
            tickers.append(ticker)

    return tickers[:MAX_SYMBOLS_PER_CYCLE]



# ============================================================
# DISCOUNT INTELLIGENCE V1
#
# Purpose:
# "Cheap" is not automatically "good".
# We combine:
#   1) analyst target gap (when available)
#   2) distance below 52-week high
#   3) technical quality / not-overextended structure
#   4) existing HANZ Swing score
#
# Missing analyst data is never invented. In that case HANZ labels
# the result TECHNICAL_ONLY rather than pretending it is an
# analyst-confirmed valuation discount.
# ============================================================


def _latest_two_values(df, row_candidates):
    """Return latest and previous numeric values from a financial statement row."""
    if df is None or getattr(df, "empty", True):
        return None, None

    row_name = None

    for candidate in row_candidates:
        if candidate in df.index:
            row_name = candidate
            break

    if row_name is None:
        return None, None

    series = df.loc[row_name]

    try:
        series = series.dropna()
    except Exception:
        return None, None

    values = []

    for value in series.tolist():
        number = safe_float(value)
        if number is not None:
            values.append(number)

    if not values:
        return None, None

    latest = values[0]
    previous = values[1] if len(values) > 1 else None
    return latest, previous


def _growth_pct(latest, previous):
    if (
        latest is None
        or previous is None
        or previous == 0
    ):
        return None

    # For negative-to-positive or negative-base cases, percentage growth
    # becomes misleading. We leave it unavailable and score profitability
    # separately instead of inventing a percentage.
    if previous < 0:
        return None

    return (latest - previous) / abs(previous) * 100


def _safe_ratio_pct(numerator, denominator):
    if (
        numerator is None
        or denominator in (None, 0)
    ):
        return None
    return numerator / denominator * 100


def get_company_intelligence(
    ticker,
    *,
    include_analyst=True,
    include_fundamental=True,
):
    """Fetch analyst + fundamental data once for one ticker.

    Source: yfinance/Yahoo public financial endpoints.
    Missing fields remain None. HANZ never fabricates missing fundamentals.
    """
    symbol = normalize_ticker(ticker)

    if not symbol:
        return {
            "analyst": {},
            "fundamental": {},
        }

    analyst = {}
    fundamental = {}

    try:
        obj = yf.Ticker(symbol)

        # ---------------------------------
        # Analyst targets
        # ---------------------------------
        if include_analyst:
            try:
                targets = obj.get_analyst_price_targets()

                if isinstance(targets, dict):
                    analyst = {
                        "current": safe_float(
                            targets.get("current")
                        ),
                        "low": safe_float(
                            targets.get("low")
                        ),
                        "high": safe_float(
                            targets.get("high")
                        ),
                        "mean": safe_float(
                            targets.get("mean")
                        ),
                        "median": safe_float(
                            targets.get("median")
                        ),
                    }
            except Exception as exc:
                print(
                    f"SWING INTEL {clean_ticker(ticker)} "
                    f"analyst unavailable: {exc}",
                    flush=True,
                )

        # ---------------------------------
        # Fundamental statements
        # ---------------------------------
        if include_fundamental:
            try:
                income = obj.get_income_stmt(
                    freq="yearly"
                )
            except Exception:
                income = None

            try:
                balance = obj.get_balance_sheet(
                    freq="yearly"
                )
            except Exception:
                balance = None

            try:
                cashflow = obj.get_cashflow(
                    freq="yearly"
                )
            except Exception:
                cashflow = None

            try:
                info = obj.get_info()
                if not isinstance(info, dict):
                    info = {}
            except Exception:
                info = {}

            revenue, revenue_prev = _latest_two_values(
                income,
                [
                    "Total Revenue",
                    "Operating Revenue",
                ],
            )

            net_income, net_income_prev = _latest_two_values(
                income,
                [
                    "Net Income",
                    "Net Income Common Stockholders",
                ],
            )

            operating_income, operating_income_prev = _latest_two_values(
                income,
                [
                    "Operating Income",
                ],
            )

            gross_profit, gross_profit_prev = _latest_two_values(
                income,
                [
                    "Gross Profit",
                ],
            )

            total_debt, total_debt_prev = _latest_two_values(
                balance,
                [
                    "Total Debt",
                    "Total Debt And Capital Lease Obligation",
                ],
            )

            equity, equity_prev = _latest_two_values(
                balance,
                [
                    "Stockholders Equity",
                    "Total Equity Gross Minority Interest",
                    "Common Stock Equity",
                ],
            )

            total_assets, total_assets_prev = _latest_two_values(
                balance,
                [
                    "Total Assets",
                ],
            )

            operating_cf, operating_cf_prev = _latest_two_values(
                cashflow,
                [
                    "Operating Cash Flow",
                    "Cash Flow From Continuing Operating Activities",
                ],
            )

            capex, capex_prev = _latest_two_values(
                cashflow,
                [
                    "Capital Expenditure",
                ],
            )

            revenue_growth = _growth_pct(
                revenue,
                revenue_prev,
            )

            net_income_growth = _growth_pct(
                net_income,
                net_income_prev,
            )

            operating_income_growth = _growth_pct(
                operating_income,
                operating_income_prev,
            )

            roe = safe_float(
                info.get("returnOnEquity")
            )
            if roe is not None:
                roe *= 100
            else:
                roe = _safe_ratio_pct(
                    net_income,
                    equity,
                )

            roa = safe_float(
                info.get("returnOnAssets")
            )
            if roa is not None:
                roa *= 100
            else:
                roa = _safe_ratio_pct(
                    net_income,
                    total_assets,
                )

            debt_to_equity = safe_float(
                info.get("debtToEquity")
            )
            if debt_to_equity is not None:
                # Yahoo convention is typically percentage points.
                debt_to_equity /= 100
            elif (
                total_debt is not None
                and equity not in (None, 0)
            ):
                debt_to_equity = (
                    total_debt / equity
                )

            net_margin = safe_float(
                info.get("profitMargins")
            )
            if net_margin is not None:
                net_margin *= 100
            else:
                net_margin = _safe_ratio_pct(
                    net_income,
                    revenue,
                )

            operating_margin = safe_float(
                info.get("operatingMargins")
            )
            if operating_margin is not None:
                operating_margin *= 100
            else:
                operating_margin = _safe_ratio_pct(
                    operating_income,
                    revenue,
                )

            gross_margin = safe_float(
                info.get("grossMargins")
            )
            if gross_margin is not None:
                gross_margin *= 100
            else:
                gross_margin = _safe_ratio_pct(
                    gross_profit,
                    revenue,
                )

            pe_ratio = safe_float(
                info.get("trailingPE")
            )
            pb_ratio = safe_float(
                info.get("priceToBook")
            )

            sector = str(
                info.get("sector")
                or ""
            ).strip() or None

            industry = str(
                info.get("industry")
                or ""
            ).strip() or None

            free_cf = None
            if operating_cf is not None:
                if capex is not None:
                    free_cf = (
                        operating_cf
                        + capex
                        if capex < 0
                        else operating_cf - capex
                    )
                else:
                    free_cf = operating_cf

            fundamental = {
                "sector": sector,
                "industry": industry,
                "revenue": revenue,
                "revenue_prev": revenue_prev,
                "revenue_growth_pct": safe_float(
                    revenue_growth
                ),
                "net_income": net_income,
                "net_income_prev": net_income_prev,
                "net_income_growth_pct": safe_float(
                    net_income_growth
                ),
                "operating_income_growth_pct": safe_float(
                    operating_income_growth
                ),
                "roe_pct": safe_float(roe),
                "roa_pct": safe_float(roa),
                "debt_to_equity": safe_float(
                    debt_to_equity
                ),
                "operating_cash_flow": operating_cf,
                "free_cash_flow": safe_float(free_cf),
                "net_margin_pct": safe_float(
                    net_margin
                ),
                "operating_margin_pct": safe_float(
                    operating_margin
                ),
                "gross_margin_pct": safe_float(
                    gross_margin
                ),
                "pe_ratio": pe_ratio,
                "pb_ratio": pb_ratio,
            }

    except Exception as exc:
        print(
            f"SWING INTEL {clean_ticker(ticker)} "
            f"company data unavailable: {exc}",
            flush=True,
        )

    return {
        "analyst": analyst,
        "fundamental": fundamental,
    }


def fundamental_intelligence_v1(
    fundamental,
):
    """Universal fundamental quality score 0-100.

    This is deliberately sector-agnostic V1. Banks/miners/property can
    receive sector-specific models later without changing table structure.
    """
    f = fundamental or {}

    components = []
    evidence = []

    revenue_growth = safe_float(
        f.get("revenue_growth_pct")
    )
    net_income_growth = safe_float(
        f.get("net_income_growth_pct")
    )
    roe = safe_float(
        f.get("roe_pct")
    )
    debt_to_equity = safe_float(
        f.get("debt_to_equity")
    )
    operating_cf = safe_float(
        f.get("operating_cash_flow")
    )
    free_cf = safe_float(
        f.get("free_cash_flow")
    )
    net_margin = safe_float(
        f.get("net_margin_pct")
    )
    operating_margin = safe_float(
        f.get("operating_margin_pct")
    )

    # Revenue growth — 20
    if revenue_growth is not None:
        if revenue_growth >= 15:
            points = 20
        elif revenue_growth >= 8:
            points = 16
        elif revenue_growth >= 3:
            points = 12
        elif revenue_growth >= 0:
            points = 8
        elif revenue_growth >= -5:
            points = 4
        else:
            points = 0
        components.append(("revenue_growth", points, 20))
        evidence.append(
            f"revenue growth {revenue_growth:+.1f}%"
        )

    # Net income growth — 20
    if net_income_growth is not None:
        if net_income_growth >= 20:
            points = 20
        elif net_income_growth >= 10:
            points = 16
        elif net_income_growth >= 3:
            points = 12
        elif net_income_growth >= 0:
            points = 8
        elif net_income_growth >= -10:
            points = 4
        else:
            points = 0
        components.append(("earnings_growth", points, 20))
        evidence.append(
            f"net income growth {net_income_growth:+.1f}%"
        )
    elif safe_float(f.get("net_income")) is not None:
        # Profitability direction still matters if growth cannot be
        # computed because the previous base was negative.
        net_income = safe_float(f.get("net_income"))
        points = 10 if net_income > 0 else 0
        components.append(("profitability", points, 20))
        evidence.append(
            "net income positive"
            if net_income > 0
            else "net income negative"
        )

    # ROE — 20
    if roe is not None:
        if roe >= 20:
            points = 20
        elif roe >= 15:
            points = 17
        elif roe >= 10:
            points = 13
        elif roe >= 5:
            points = 8
        elif roe > 0:
            points = 4
        else:
            points = 0
        components.append(("roe", points, 20))
        evidence.append(f"ROE {roe:.1f}%")

    # Debt / equity — 15
    if debt_to_equity is not None:
        if debt_to_equity <= 0.5:
            points = 15
        elif debt_to_equity <= 1.0:
            points = 12
        elif debt_to_equity <= 1.5:
            points = 8
        elif debt_to_equity <= 2.5:
            points = 4
        else:
            points = 0
        components.append(("leverage", points, 15))
        evidence.append(
            f"D/E {debt_to_equity:.2f}x"
        )

    # Operating cash flow — 15
    if operating_cf is not None:
        points = 15 if operating_cf > 0 else 0
        components.append(("operating_cf", points, 15))
        evidence.append(
            "operating cash flow positive"
            if operating_cf > 0
            else "operating cash flow negative"
        )

    # Margin quality — 10
    margin = (
        operating_margin
        if operating_margin is not None
        else net_margin
    )
    if margin is not None:
        if margin >= 20:
            points = 10
        elif margin >= 12:
            points = 8
        elif margin >= 7:
            points = 6
        elif margin > 0:
            points = 3
        else:
            points = 0
        components.append(("margin", points, 10))
        evidence.append(
            f"margin {margin:.1f}%"
        )

    max_available = sum(
        max_points
        for _, _, max_points in components
    )
    raw_points = sum(
        points
        for _, points, _ in components
    )

    if max_available == 0:
        score = None
        label = "NO_FUNDAMENTAL_DATA"
        confidence = "NONE"
    else:
        score = round(
            raw_points / max_available * 100,
            1,
        )

        coverage = max_available / 100

        if coverage >= 0.80:
            confidence = "HIGH"
        elif coverage >= 0.55:
            confidence = "MEDIUM"
        else:
            confidence = "LOW"

        if score >= 75:
            label = "GOOD"
        elif score >= 55:
            label = "ACCEPTABLE"
        elif score >= 40:
            label = "WEAK"
        else:
            label = "BAD"

    return {
        "fundamental_score": score,
        "fundamental_label": label,
        "fundamental_confidence": confidence,
        "fundamental_coverage_pct": round(
            max_available,
            1,
        ),
        "fundamental_reason": "; ".join(evidence),
        **f,
    }



def discount_intelligence_v2(
    ticker,
    daily,
    weekly,
    result,
    analyst,
    fundamental_result,
):
    price = safe_float(daily.get("price"))
    score = safe_float(result.get("score")) or 0

    target_mean = safe_float(analyst.get("mean"))
    target_low = safe_float(analyst.get("low"))
    target_high = safe_float(analyst.get("high"))
    target_median = safe_float(analyst.get("median"))

    analyst_upside_pct = None
    target_discount_pct = None

    if (
        price not in (None, 0)
        and target_mean not in (None, 0)
    ):
        analyst_upside_pct = (
            (target_mean - price) / price * 100
        )
        target_discount_pct = (
            (target_mean - price) / target_mean * 100
        )

    # ---------------------
    # Component A: analyst valuation gap — 30 points
    # ---------------------
    analyst_points = None

    if target_discount_pct is not None:
        if target_discount_pct >= 35:
            analyst_points = 30
        elif target_discount_pct >= 25:
            analyst_points = 26
        elif target_discount_pct >= 15:
            analyst_points = 21
        elif target_discount_pct >= 8:
            analyst_points = 15
        elif target_discount_pct >= 3:
            analyst_points = 7
        else:
            analyst_points = 0

    # ---------------------
    # Component B: discount to 52-week high — 15 points
    # ---------------------
    week52_discount = safe_float(
        daily.get("week52_discount_pct")
    )

    if week52_discount is None:
        week52_points = 0
    elif week52_discount >= 30:
        week52_points = 15
    elif week52_discount >= 20:
        week52_points = 13
    elif week52_discount >= 10:
        week52_points = 10
    elif week52_discount >= 5:
        week52_points = 5
    else:
        week52_points = 1

    # ---------------------
    # Component C: technical quality — 20 points
    # Prevents "cheap because broken" from looking attractive.
    # ---------------------
    technical_points = 0

    if result.get("weekly_trend") == "BULLISH":
        technical_points += 8

    if result.get("daily_trend") == "BULLISH":
        technical_points += 5

    rsi_d = safe_float(daily.get("rsi14"))
    if rsi_d is not None and 50 <= rsi_d <= 70:
        technical_points += 3

    ema20 = safe_float(daily.get("ema20"))
    if (
        price not in (None, 0)
        and ema20 not in (None, 0)
        and price >= ema20
    ):
        extension_pct = (
            (price - ema20) / ema20 * 100
        )
        if extension_pct <= 8:
            technical_points += 4
        elif extension_pct <= 12:
            technical_points += 2

    # ---------------------
    # Component D: existing Swing score — 20 points
    # ---------------------
    swing_points = max(
        0,
        min(20, score * 2),
    )

    # ---------------------
    # Component E: fundamental quality — 15 points
    # ---------------------
    fundamental_score = safe_float(
        fundamental_result.get("fundamental_score")
        if fundamental_result else None
    )

    if fundamental_score is None:
        fundamental_points = None
    else:
        fundamental_points = max(
            0,
            min(
                15,
                fundamental_score / 100 * 15,
            ),
        )

    if analyst_points is not None:
        raw_score = (
            analyst_points
            + week52_points
            + technical_points
            + swing_points
            + (
                fundamental_points
                if fundamental_points is not None
                else 0
            )
        )

        max_score = (
            85
            + (
                15
                if fundamental_points is not None
                else 0
            )
        )

        raw_score = (
            raw_score / max_score * 100
        )
        discount_score = round(
            max(0, min(100, raw_score)),
            1,
        )
        confidence = "ANALYST_CONFIRMED"

        if (
            discount_score >= 75
            and result.get("state") == "SWING_BUY"
            and analyst_upside_pct is not None
            and analyst_upside_pct > 0
        ):
            label = "DISCOUNT_CONFIRMED"
        elif discount_score >= 65:
            label = "QUALITY_DISCOUNT"
        elif discount_score >= 50:
            label = "DISCOUNT_WATCH"
        else:
            label = "NOT_DISCOUNT"

    else:
        # No analyst target: normalize the factors we truly have.
        available = (
            week52_points
            + technical_points
            + swing_points
            + (
                fundamental_points
                if fundamental_points is not None
                else 0
            )
        )

        available_max = (
            55
            + (
                15
                if fundamental_points is not None
                else 0
            )
        )

        discount_score = round(
            max(
                0,
                min(
                    100,
                    available / available_max * 100,
                ),
            ),
            1,
        )

        confidence = (
            "FUNDAMENTAL_TECHNICAL"
            if fundamental_points is not None
            else "TECHNICAL_ONLY"
        )

        if discount_score >= 75:
            label = "TECHNICAL_VALUE_ZONE"
        elif discount_score >= 55:
            label = "FAIR_TECHNICAL_VALUE"
        else:
            label = "EXTENDED_OR_WEAK_VALUE"

    reason_parts = []

    if target_mean is not None and price is not None:
        reason_parts.append(
            f"analyst mean {target_mean:.2f}"
        )
        if analyst_upside_pct is not None:
            reason_parts.append(
                f"analyst upside {analyst_upside_pct:+.1f}%"
            )
    else:
        reason_parts.append(
            "analyst target unavailable"
        )

    if week52_discount is not None:
        reason_parts.append(
            f"{week52_discount:.1f}% below 52W high"
        )

    reason_parts.append(
        f"technical quality {technical_points}/20"
    )
    reason_parts.append(
        f"swing {int(score)}/10"
    )

    if fundamental_score is not None:
        reason_parts.append(
            f"fundamental {fundamental_score:.0f}/100 "
            f"{fundamental_result.get('fundamental_label')}"
        )
    else:
        reason_parts.append(
            "fundamental unavailable"
        )

    return {
        "analyst_target_mean": target_mean,
        "analyst_target_median": target_median,
        "analyst_target_low": target_low,
        "analyst_target_high": target_high,
        "analyst_upside_pct": safe_float(
            analyst_upside_pct
        ),
        "target_discount_pct": safe_float(
            target_discount_pct
        ),
        "week52_high": daily.get("week52_high"),
        "week52_low": daily.get("week52_low"),
        "week52_discount_pct": daily.get(
            "week52_discount_pct"
        ),
        "week52_position_pct": daily.get(
            "week52_position_pct"
        ),
        "discount_score": discount_score,
        "discount_label": label,
        "discount_confidence": confidence,
        "discount_reason": "; ".join(reason_parts),
        "fundamental_score": fundamental_score,
        "fundamental_label": (
            fundamental_result.get("fundamental_label")
            if fundamental_result else None
        ),
        "fundamental_confidence": (
            fundamental_result.get("fundamental_confidence")
            if fundamental_result else None
        ),
    }



def upsert_monitor(
    ticker,
    daily,
    weekly,
    result,
    levels,
    discount,
    fundamental,
):
    payload = {
        "ticker": clean_ticker(ticker),
        "state": result["state"],
        "score": result["score"],
        "price": daily["price"],
        "daily_trend": result["daily_trend"],
        "weekly_trend": result["weekly_trend"],
        "daily_rsi": daily["rsi14"],
        "weekly_rsi": weekly["rsi14"],
        "daily_rvol": daily["rvol20"],
        "breakout": result["breakout"],
        "breakout_level": daily["prior_high20"],
        "entry_price": levels.get("entry_price"),
        "entry_low": levels.get("entry_low"),
        "entry_high": levels.get("entry_high"),
        "entry_status": levels.get("entry_status"),
        "entry_note": levels.get("entry_note"),
        "stop_loss": levels["stop_loss"],
        "target_1": levels["target_1"],
        "target_2": levels["target_2"],
        "rr_target_1": levels.get("rr_target_1"),
        "rr_target_2": levels.get("rr_target_2"),
        "target_mode": levels.get("target_mode"),
        "analyst_target_mean": discount.get("analyst_target_mean"),
        "analyst_target_median": discount.get("analyst_target_median"),
        "analyst_target_low": discount.get("analyst_target_low"),
        "analyst_target_high": discount.get("analyst_target_high"),
        "analyst_upside_pct": discount.get("analyst_upside_pct"),
        "target_discount_pct": discount.get("target_discount_pct"),
        "week52_high": discount.get("week52_high"),
        "week52_low": discount.get("week52_low"),
        "week52_discount_pct": discount.get("week52_discount_pct"),
        "week52_position_pct": discount.get("week52_position_pct"),
        "discount_score": discount.get("discount_score"),
        "discount_label": discount.get("discount_label"),
        "discount_confidence": discount.get("discount_confidence"),
        "discount_reason": discount.get("discount_reason"),
        "fundamental_score": discount.get("fundamental_score"),
        "fundamental_label": discount.get("fundamental_label"),
        "fundamental_confidence": discount.get("fundamental_confidence"),
        "fundamental_coverage_pct": fundamental.get("fundamental_coverage_pct"),
        "fundamental_reason": fundamental.get("fundamental_reason"),
        "sector": fundamental.get("sector"),
        "industry": fundamental.get("industry"),
        "revenue_growth_pct": fundamental.get("revenue_growth_pct"),
        "net_income_growth_pct": fundamental.get("net_income_growth_pct"),
        "roe_pct": fundamental.get("roe_pct"),
        "roa_pct": fundamental.get("roa_pct"),
        "debt_to_equity": fundamental.get("debt_to_equity"),
        "operating_cash_flow": fundamental.get("operating_cash_flow"),
        "free_cash_flow": fundamental.get("free_cash_flow"),
        "net_margin_pct": fundamental.get("net_margin_pct"),
        "operating_margin_pct": fundamental.get("operating_margin_pct"),
        "pe_ratio": fundamental.get("pe_ratio"),
        "pb_ratio": fundamental.get("pb_ratio"),
        "evidence": "; ".join(
            result["evidence"]
        ),
        "daily_bar_at": daily["bar_at"],
        "weekly_bar_at": weekly["bar_at"],
        "updated_at": now_iso(),
    }

    supabase_request(
        "POST",
        "hanz_swing_signal_monitor"
        "?on_conflict=ticker",
        payload,
        prefer=(
            "resolution=merge-duplicates,"
            "return=minimal"
        ),
    )


def insert_swing_signal(
    ticker,
    daily,
    result,
    levels,
):
    # Only log actionable SWING_BUY transition.
    ticker_encoded = urllib.parse.quote(
        clean_ticker(ticker), safe=""
    )

    existing = supabase_request(
        "GET",
        "hanz_swing_signals"
        f"?ticker=eq.{ticker_encoded}"
        "&signal_type=eq.SWING_BUY"
        "&select=id,created_at"
        "&order=created_at.desc"
        "&limit=1",
    ) or []

    # One SWING_BUY record per ticker per calendar day.
    if existing:
        created = str(
            existing[0].get("created_at")
            or ""
        )[:10]
        if created == utc_now().date().isoformat():
            return

    payload = {
        "ticker": clean_ticker(ticker),
        "signal_type": "SWING_BUY",
        "price": daily["price"],
        "entry_price": levels.get("entry_price"),
        "entry_low": levels.get("entry_low"),
        "entry_high": levels.get("entry_high"),
        "entry_status": levels.get("entry_status"),
        "score": result["score"],
        "stop_loss": levels["stop_loss"],
        "target_1": levels["target_1"],
        "target_2": levels["target_2"],
        "rr_target_1": levels.get("rr_target_1"),
        "rr_target_2": levels.get("rr_target_2"),
        "target_mode": levels.get("target_mode"),
        "reason": "; ".join(
            result["evidence"]
        ),
        "created_at": now_iso(),
    }

    supabase_request(
        "POST",
        "hanz_swing_signals",
        payload,
        prefer="return=minimal",
    )


def scan_symbol(ticker):
    daily_df = download_frame(
        ticker,
        DAILY_INTERVAL,
        DAILY_PERIOD,
    )

    weekly_df = download_frame(
        ticker,
        WEEKLY_INTERVAL,
        WEEKLY_PERIOD,
    )

    daily = daily_metrics(daily_df)
    weekly = weekly_metrics(weekly_df)

    result = swing_score(
        daily,
        weekly,
    )

    company_intel = {
        "analyst": {},
        "fundamental": {},
    }

    if (
        result.get("state") in DISCOUNT_ANALYST_STATES
        or result.get("state") in FUNDAMENTAL_STATES
    ):
        company_intel = get_company_intelligence(
            ticker,
            include_analyst=(
                result.get("state")
                in DISCOUNT_ANALYST_STATES
            ),
            include_fundamental=(
                result.get("state")
                in FUNDAMENTAL_STATES
            ),
        )

        if FUNDAMENTAL_FETCH_DELAY_SECONDS > 0:
            time.sleep(
                FUNDAMENTAL_FETCH_DELAY_SECONDS
            )

    fundamental = fundamental_intelligence_v1(
        company_intel.get("fundamental")
    )

    discount = discount_intelligence_v2(
        ticker,
        daily,
        weekly,
        result,
        company_intel.get("analyst") or {},
        fundamental,
    )

    levels = risk_levels(
        daily,
        result=result,
        discount=discount,
        fundamental=fundamental,
    )

    upsert_monitor(
        ticker,
        daily,
        weekly,
        result,
        levels,
        discount,
        fundamental,
    )

    if result["state"] == "SWING_BUY":
        insert_swing_signal(
            ticker,
            daily,
            result,
            levels,
        )

    print(
        f"SWING {clean_ticker(ticker)} "
        f"{result['state']} "
        f"score={result['score']}/10 "
        f"discount={discount['discount_score']}/100 "
        f"{discount['discount_label']} "
        f"fundamental={fundamental.get('fundamental_score')}/100 "
        f"{fundamental.get('fundamental_label')} "
        f"entry={levels.get('entry_low')}-{levels.get('entry_high')} "
        f"T1={levels.get('target_1')} "
        f"T2={levels.get('target_2')} "
        f"{levels.get('target_mode')}",
        flush=True,
    )

    return result["state"]


def run_cycle():
    market = idx_market_session()
    now_wib = jakarta_now()

    previous_day = previous_idx_trading_day(
        now_wib.date()
    )
    next_day = next_idx_trading_day(
        now_wib.date()
    )

    print(
        "IDX MARKET GATE: "
        f"{market['state']} | "
        f"reason={market['reason']} | "
        f"WIB={now_wib.strftime('%Y-%m-%d %H:%M')} | "
        f"previous={previous_day} | "
        f"next={next_day}",
        flush=True,
    )

    if not market["is_trading_day"]:
        print(
            "SWING cycle skipped: IDX is not a trading day. "
            "No new signal, portfolio trigger, alert or push.",
            flush=True,
        )
        return

    # During active sessions / lunch, only monitor portfolio risk.
    # Universe SWING_BUY generation waits for the completed daily bar.
    if not market["allow_final_scan"]:
        if market["allow_portfolio_monitor"]:
            portfolio_summary = monitor_swing_portfolio(
                allow_structural_exit=False
            )
            print(
                "SWING intraday portfolio monitor complete: "
                + json.dumps(portfolio_summary)
                + " | structural exits=DEFERRED_TO_POST_CLOSE",
                flush=True,
            )
        else:
            print(
                "SWING cycle skipped outside IDX operating window.",
                flush=True,
            )
        return

    universe = fetch_universe()

    print(
        f"SWING FINAL SCAN universe: {len(universe)}",
        flush=True,
    )

    counts = {
        "SWING_BUY": 0,
        "SWING_CONFIRMING": 0,
        "SWING_WATCH": 0,
        "NO_SETUP": 0,
        "ERROR": 0,
    }

    for ticker in universe:
        try:
            state = scan_symbol(ticker)
            counts[state] = (
                counts.get(state, 0) + 1
            )
        except Exception as exc:
            counts["ERROR"] += 1
            print(
                f"SWING {ticker} failed: {exc}",
                flush=True,
            )

    portfolio_summary = monitor_swing_portfolio(
        allow_structural_exit=True
    )

    print(
        "SWING FINAL cycle complete: "
        + json.dumps(counts)
        + " | portfolio="
        + json.dumps(portfolio_summary),
        flush=True,
    )


def main():
    print(
        "HANZ SWING / WEEKLY ENGINE START",
        flush=True,
    )

    print(
        f"Daily={DAILY_INTERVAL}/{DAILY_PERIOD} | "
        f"Weekly={WEEKLY_INTERVAL}/{WEEKLY_PERIOD} | "
        f"Cycle={SWING_INTERVAL}s | "
        f"Portfolio monitor=ON | "
        f"IDX calendar gate=ON (Asia/Jakarta) | "
        f"Trailing={TRAILING_ATR_MULTIPLIER_T1:.1f}x/"
        f"{TRAILING_ATR_MULTIPLIER_T2:.1f}x ATR",
        flush=True,
    )

    while True:
        try:
            run_cycle()
        except Exception as exc:
            print(
                f"SWING cycle failed: {exc}",
                flush=True,
            )

        if RUN_ONCE:
            break

        print(
            f"SWING engine sleeping "
            f"{SWING_INTERVAL} seconds...",
            flush=True,
        )

        time.sleep(SWING_INTERVAL)


if __name__ == "__main__":
    main()
