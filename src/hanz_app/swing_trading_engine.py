
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

    return {
        "price": price,
        "open": safe_float(df["Open"].iloc[-1]),
        "high": safe_float(df["High"].iloc[-1]),
        "low": safe_float(df["Low"].iloc[-1]),
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


def risk_levels(daily):
    price = daily["price"]
    atr14 = daily["atr14"]
    prior_low20 = daily["prior_low20"]

    if (
        price is None
        or atr14 is None
        or atr14 <= 0
    ):
        return {
            "stop_loss": None,
            "target_1": None,
            "target_2": None,
            "risk_per_share": None,
        }

    atr_stop = price - (2.0 * atr14)

    if prior_low20 is None:
        stop = atr_stop
    else:
        # Use the closer protective level while
        # keeping it below current price.
        stop = max(
            atr_stop,
            prior_low20,
        )

    if stop >= price:
        stop = atr_stop

    risk = price - stop

    return {
        "stop_loss": round(stop, 4),
        "target_1": round(
            price + (2.0 * risk), 4
        ),
        "target_2": round(
            price + (3.0 * risk), 4
        ),
        "risk_per_share": round(
            risk, 4
        ),
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
        daily_breakdown
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
        reached_t1
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


def monitor_swing_portfolio():
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


def upsert_monitor(
    ticker,
    daily,
    weekly,
    result,
    levels,
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
        "stop_loss": levels["stop_loss"],
        "target_1": levels["target_1"],
        "target_2": levels["target_2"],
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
        "score": result["score"],
        "stop_loss": levels["stop_loss"],
        "target_1": levels["target_1"],
        "target_2": levels["target_2"],
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

    levels = risk_levels(daily)

    upsert_monitor(
        ticker,
        daily,
        weekly,
        result,
        levels,
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
        f"score={result['score']}/10",
        flush=True,
    )

    return result["state"]


def run_cycle():
    universe = fetch_universe()

    print(
        f"SWING universe: {len(universe)}",
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

    portfolio_summary = monitor_swing_portfolio()

    print(
        "SWING cycle complete: "
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
