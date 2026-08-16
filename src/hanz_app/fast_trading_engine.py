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

# Firebase Admin is optional at import time so the trading engine
# keeps running even before Railway has the dependency/credential.
try:
    import firebase_admin
    from firebase_admin import credentials, messaging
except Exception:
    firebase_admin = None
    credentials = None
    messaging = None



SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_SECRET_KEY = os.getenv("SUPABASE_SECRET_KEY", "")

FAST_STATE_ID = "bei-fast"

FAST_INTERVAL = int(os.getenv("HANZ_FAST_INTERVAL", "60"))
RUN_ONCE = os.getenv("HANZ_FAST_RUN_ONCE", "0") == "1"

INTRADAY_INTERVAL = os.getenv("HANZ_FAST_TIMEFRAME", "1m")
INTRADAY_PERIOD = os.getenv("HANZ_FAST_PERIOD", "1d")

CONFIRM_INTERVAL = os.getenv("HANZ_CONFIRM_TIMEFRAME", "5m")
CONFIRM_PERIOD = os.getenv("HANZ_CONFIRM_PERIOD", "5d")

MAX_DATA_AGE_SECONDS = int(
    os.getenv("HANZ_MAX_DATA_AGE_SECONDS", "600")
)

ALERT_COOLDOWN_SECONDS = int(
    os.getenv("HANZ_ALERT_COOLDOWN_SECONDS", "900")
)

TRAILING_ATR_MULTIPLIER_T1 = float(
    os.getenv("HANZ_TRAILING_ATR_MULTIPLIER_T1", "1.5")
)

TRAILING_ATR_MULTIPLIER_T2 = float(
    os.getenv("HANZ_TRAILING_ATR_MULTIPLIER_T2", "1.0")
)

FIREBASE_SERVICE_ACCOUNT_JSON = os.getenv(
    "FIREBASE_SERVICE_ACCOUNT_JSON",
    "",
).strip()

PUSH_DASHBOARD_URL = os.getenv(
    "HANZ_DASHBOARD_URL",
    "https://fazabihandoko28.github.io/dashboard/",
)

JAKARTA_TZ = ZoneInfo("Asia/Jakarta")

# Deliberately quiet push policy.
PUSH_ALERT_TYPES = {
    "CONFIRMED_BUY",
    "PROTECT_PROFIT",
    "CONFIRMED_SELL",
    "STOP_LOSS",
    "TRAILING_ACTIVATED",
}

# =========================
# FAST SCOUT
# =========================
FAST_SCOUT_ENABLED = os.getenv(
    "HANZ_FAST_SCOUT_ENABLED",
    "1",
).strip() not in {"0", "false", "False"}

FAST_SCOUT_BATCH_SIZE = int(
    os.getenv(
        "HANZ_FAST_SCOUT_BATCH_SIZE",
        "12",
    )
)

FAST_SCOUT_MIN_SCORE = int(
    os.getenv(
        "HANZ_FAST_SCOUT_MIN_SCORE",
        "7",
    )
)

FAST_SCOUT_CANDIDATE_MINUTES = int(
    os.getenv(
        "HANZ_FAST_SCOUT_CANDIDATE_MINUTES",
        "30",
    )
)

FAST_SCOUT_CURSOR_FILE = os.getenv(
    "HANZ_FAST_SCOUT_CURSOR_FILE",
    "/tmp/hanz_fast_scout_cursor.txt",
)

_FIREBASE_APP = None


def utc_now():
    return datetime.now(timezone.utc)


def now_iso():
    return utc_now().isoformat()


def normalize_ticker(ticker):
    ticker = str(ticker).strip().upper()

    if not ticker:
        return None

    if not ticker.endswith(".JK"):
        ticker = f"{ticker}.JK"

    return ticker


def clean_ticker(ticker):
    return str(ticker).upper().replace(".JK", "")


def safe_float(value):
    try:
        if value is None:
            return None

        number = float(value)

        if math.isnan(number):
            return None

        return number

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


def supabase_request(
    method,
    endpoint,
    payload=None,
    prefer=None,
):
    if not SUPABASE_URL:
        raise RuntimeError("SUPABASE_URL is missing")

    if not SUPABASE_SECRET_KEY:
        raise RuntimeError("SUPABASE_SECRET_KEY is missing")

    url = f"{SUPABASE_URL}/rest/v1/{endpoint}"

    headers = {
        "apikey": SUPABASE_SECRET_KEY,
        "Content-Type": "application/json",
    }

    if prefer:
        headers["Prefer"] = prefer

    data = None

    if payload is not None:
        data = json.dumps(
            payload,
            default=str,
        ).encode("utf-8")

    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers=headers,
    )

    with urllib.request.urlopen(
        request,
        timeout=30,
    ) as response:

        raw = response.read()

        if not raw:
            return None

        return json.loads(raw.decode("utf-8"))


def fetch_portfolio():
    query = urllib.parse.urlencode(
        {
            "select": "*",
            "status": "eq.OPEN",
        }
    )

    rows = supabase_request(
        "GET",
        f"hanz_portfolio?{query}",
    )

    return rows or []


def update_portfolio_row(portfolio_id, payload):
    if portfolio_id is None or not payload:
        return

    encoded_id = urllib.parse.quote(str(portfolio_id), safe="")

    supabase_request(
        "PATCH",
        f"hanz_portfolio?id=eq.{encoded_id}",
        payload,
        prefer="return=minimal",
    )


def fetch_watchlist():
    query = urllib.parse.urlencode(
        {
            "select": "*",
        }
    )

    rows = supabase_request(
        "GET",
        f"hanz_watchlist?{query}",
    )

    now = utc_now()
    active = []

    for row in rows or []:
        expires_at = row.get("expires_at")

        if expires_at:
            try:
                expiry = datetime.fromisoformat(
                    expires_at.replace("Z", "+00:00")
                )

                if expiry < now:
                    continue

            except Exception:
                pass

        active.append(row)

    return active


def download_data(
    ticker,
    interval,
    period,
):
    symbol = normalize_ticker(ticker)

    started = time.time()

    frame = yf.download(
        symbol,
        interval=interval,
        period=period,
        auto_adjust=False,
        progress=False,
        threads=False,
    )

    latency = round(
        time.time() - started,
        3,
    )

    if frame is None or frame.empty:
        raise RuntimeError(
            f"No market data for {symbol}"
        )

    if isinstance(
        frame.columns,
        pd.MultiIndex,
    ):
        frame.columns = [
            col[0]
            for col in frame.columns
        ]

    frame = frame.dropna(
        subset=["Close"]
    )

    if frame.empty:
        raise RuntimeError(
            f"Empty close data for {symbol}"
        )

    return symbol, frame, latency


def last_timestamp_utc(frame):
    ts = frame.index[-1]

    if getattr(ts, "tzinfo", None) is None:
        ts = ts.tz_localize("UTC")
    else:
        ts = ts.tz_convert("UTC")

    return ts


def data_age_seconds(frame):
    ts = last_timestamp_utc(frame)

    age = (
        utc_now()
        - ts.to_pydatetime()
    ).total_seconds()

    return max(0, int(age))


def ema(series, length):
    return series.ewm(
        span=length,
        adjust=False,
    ).mean()


def rsi(series, length=14):
    delta = series.diff()

    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.rolling(length).mean()
    avg_loss = loss.rolling(length).mean()

    rs = avg_gain / avg_loss.replace(
        0,
        float("nan"),
    )

    return 100 - (100 / (1 + rs))


def atr(frame, length=14):
    high = frame["High"]
    low = frame["Low"]
    close = frame["Close"]

    previous_close = close.shift(1)

    tr = pd.concat(
        [
            high - low,
            (high - previous_close).abs(),
            (low - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)

    return tr.rolling(length).mean()


def calculate_metrics(frame):
    if len(frame) < 25:
        raise RuntimeError(
            "Not enough intraday bars"
        )

    df = frame.copy()

    df["ema9"] = ema(
        df["Close"],
        9,
    )

    df["ema21"] = ema(
        df["Close"],
        21,
    )

    df["rsi14"] = rsi(
        df["Close"],
        14,
    )

    df["atr14"] = atr(
        df,
        14,
    )

    df["avg_volume20"] = (
        df["Volume"]
        .rolling(20)
        .mean()
    )

    df["relative_volume"] = (
        df["Volume"]
        / df["avg_volume20"]
    )

    df["prior_high20"] = (
        df["High"]
        .rolling(20)
        .max()
        .shift(1)
    )

    df["prior_low20"] = (
        df["Low"]
        .rolling(20)
        .min()
        .shift(1)
    )

    row = df.iloc[-1]

    return {
        "price": safe_float(row["Close"]),
        "open": safe_float(row["Open"]),
        "high": safe_float(row["High"]),
        "low": safe_float(row["Low"]),
        "volume": safe_float(row["Volume"]),
        "ema9": safe_float(row["ema9"]),
        "ema21": safe_float(row["ema21"]),
        "rsi": safe_float(row["rsi14"]),
        "atr": safe_float(row["atr14"]),
        "relative_volume": safe_float(
            row["relative_volume"]
        ),
        "prior_high20": safe_float(
            row["prior_high20"]
        ),
        "prior_low20": safe_float(
            row["prior_low20"]
        ),
    }


def buy_confirmation(
    fast,
    confirm,
    watch,
):
    price = fast["price"]

    if price is None:
        return None

    score = 0
    evidence = []

    confirmation_price = safe_float(
        watch.get("confirmation_price")
    )

    entry_low = safe_float(
        watch.get("entry_zone_low")
    )

    entry_high = safe_float(
        watch.get("entry_zone_high")
    )

    invalidation = safe_float(
        watch.get("invalidation_price")
    )

    breakout_level = (
        confirmation_price
        or fast.get("prior_high20")
    )

    breakout = (
        breakout_level is not None
        and price > breakout_level
    )

    if breakout:
        score += 2
        evidence.append("price breakout")

    if (
        fast.get("ema9") is not None
        and fast.get("ema21") is not None
        and fast["ema9"] > fast["ema21"]
    ):
        score += 1
        evidence.append("1m trend positive")

    if (
        confirm.get("ema9") is not None
        and confirm.get("ema21") is not None
        and confirm["ema9"] > confirm["ema21"]
    ):
        score += 2
        evidence.append("5m trend confirmed")

    rvol = (
        fast.get("relative_volume")
        or 0
    )

    if rvol >= 1.5:
        score += 2
        evidence.append(
            f"relative volume {rvol:.2f}x"
        )

    elif rvol >= 1.2:
        score += 1
        evidence.append(
            f"volume improving {rvol:.2f}x"
        )

    fast_rsi = fast.get("rsi")
    confirm_rsi = confirm.get("rsi")

    if (
        fast_rsi is not None
        and 52 <= fast_rsi <= 78
    ):
        score += 1
        evidence.append(
            f"1m RSI {fast_rsi:.1f}"
        )

    if (
        confirm_rsi is not None
        and confirm_rsi >= 50
    ):
        score += 1
        evidence.append(
            f"5m RSI {confirm_rsi:.1f}"
        )

    early_watch = False

    if breakout_level:
        distance_pct = (
            (
                breakout_level
                - price
            )
            / price
            * 100
        )

        if (
            -0.3
            <= distance_pct
            <= 1.0
        ):
            early_watch = True

    confirmed = (
        breakout
        and score >= 7
    )

    atr_value = fast.get("atr")
    stop_loss = invalidation

    if (
        stop_loss is None
        and atr_value is not None
    ):
        stop_loss = (
            price
            - 1.5 * atr_value
        )

    target_1 = None
    target_2 = None
    risk_reward = None

    if stop_loss is not None:
        risk = price - stop_loss

        if risk > 0:
            target_1 = (
                price
                + 2 * risk
            )

            target_2 = (
                price
                + 3 * risk
            )

            risk_reward = 2.0

    return {
        "confirmed": confirmed,
        "early_watch": early_watch,
        "score": score,
        "evidence": evidence,
        "price": price,
        "entry_low": entry_low,
        "entry_high": entry_high,
        "stop_loss": stop_loss,
        "target_1": target_1,
        "target_2": target_2,
        "risk_reward": risk_reward,
    }


def apply_auto_trailing(position, fast):
    """Update peak/trailing state for one personal portfolio row.

    Rules:
    - Auto trailing is enabled by default.
    - Peak price can only rise.
    - Trailing activates at Target 1.
    - T1 uses 1.5 ATR by default.
    - T2 tightens to 1.0 ATR by default.
    - Once active, trailing stop can only rise.
    - After activation, trailing stop will not be below average buy.
    """
    if not safe_bool(position.get("auto_trailing"), True):
        return position

    price = safe_float(fast.get("price"))
    atr_value = safe_float(fast.get("atr"))

    if price is None:
        return position

    portfolio_id = position.get("id")
    avg_buy = safe_float(position.get("avg_buy"))
    target_1 = safe_float(position.get("target_1"))
    target_2 = safe_float(position.get("target_2"))
    current_peak = safe_float(position.get("peak_price"))
    current_trailing = safe_float(position.get("trailing_stop"))
    trailing_active = safe_bool(position.get("trailing_active"), False)

    peak_price = max(
        value for value in [current_peak, price] if value is not None
    )

    reached_t1 = target_1 is not None and price >= target_1
    reached_t2 = target_2 is not None and price >= target_2

    should_activate = trailing_active or reached_t1

    if reached_t2:
        multiplier = TRAILING_ATR_MULTIPLIER_T2
    else:
        multiplier = safe_float(
            position.get("trailing_atr_multiplier")
        )
        if multiplier is None or multiplier <= 0:
            multiplier = TRAILING_ATR_MULTIPLIER_T1

    new_trailing = current_trailing

    if should_activate and atr_value is not None and atr_value > 0:
        candidate = peak_price - multiplier * atr_value

        if avg_buy is not None and avg_buy > 0:
            candidate = max(candidate, avg_buy)

        if current_trailing is None:
            new_trailing = candidate
        else:
            new_trailing = max(current_trailing, candidate)

    updates = {}

    if values_different(current_peak, peak_price):
        updates["peak_price"] = peak_price

    if should_activate != trailing_active:
        updates["trailing_active"] = should_activate

        if should_activate and not position.get("trailing_activated_at"):
            updates["trailing_activated_at"] = now_iso()

    current_multiplier = safe_float(
        position.get("trailing_atr_multiplier")
    )

    if should_activate and values_different(current_multiplier, multiplier):
        updates["trailing_atr_multiplier"] = multiplier

    if should_activate and values_different(current_trailing, new_trailing):
        updates["trailing_stop"] = new_trailing
        updates["last_trailing_update_at"] = now_iso()

    if updates and portfolio_id is not None:
        just_activated = (
            should_activate
            and not trailing_active
        )

        update_portfolio_row(portfolio_id, updates)
        position.update(updates)

        if just_activated:
            user_id = position.get("user_id")
            ticker = position.get("ticker")

            title = (
                f"{clean_ticker(ticker)} "
                f"— TRAILING ACTIVATED"
            )

            message = (
                f"Target 1 reached. "
                f"Price {price:.2f} | "
                f"Peak {peak_price:.2f} | "
                f"Trailing "
                f"{new_trailing:.2f} | "
                f"{multiplier:.1f}× ATR"
            )

            queue_alert(
                ticker=ticker,
                alert_type="TRAILING_ACTIVATED",
                priority=75,
                title=title,
                message=message,
                user_id=user_id,
                portfolio_id=portfolio_id,
            )

        print(
            f"{position.get('ticker')}: trailing update "
            f"user={position.get('user_id')} "
            f"portfolio_id={portfolio_id} "
            f"peak={peak_price:.2f} "
            f"active={should_activate} "
            f"trail={new_trailing if new_trailing is not None else 'N/A'} "
            f"ATRx={multiplier:.2f}",
            flush=True,
        )

    return position


def portfolio_signal(
    fast,
    confirm,
    position,
):
    price = fast["price"]

    if price is None:
        return None

    avg_buy = safe_float(
        position.get("avg_buy")
    )

    stop_loss = safe_float(
        position.get("stop_loss")
    )

    trailing_stop = safe_float(
        position.get("trailing_stop")
    )

    auto_trailing = safe_bool(
        position.get("auto_trailing"),
        True,
    )

    trailing_active = safe_bool(
        position.get("trailing_active"),
        False,
    )

    effective_trailing_stop = trailing_stop

    if auto_trailing and not trailing_active:
        effective_trailing_stop = None

    pnl_pct = None

    if avg_buy and avg_buy > 0:
        pnl_pct = (
            price / avg_buy - 1
        ) * 100

    evidence = []
    severity = 0
    signal_type = None
    confirmed = False

    if (
        stop_loss is not None
        and price <= stop_loss
    ):
        signal_type = "STOP_LOSS"
        severity = 100
        confirmed = True
        evidence.append(
            "hard stop-loss breached"
        )

    elif (
        effective_trailing_stop is not None
        and price <= effective_trailing_stop
    ):
        signal_type = "CONFIRMED_SELL"
        severity = 90
        confirmed = True
        evidence.append(
            "trailing stop breached"
        )

    else:
        fast_negative = (
            fast.get("ema9") is not None
            and fast.get("ema21") is not None
            and fast["ema9"] < fast["ema21"]
        )

        confirm_negative = (
            confirm.get("ema9") is not None
            and confirm.get("ema21") is not None
            and confirm["ema9"] < confirm["ema21"]
        )

        breakdown = (
            fast.get("prior_low20") is not None
            and price < fast["prior_low20"]
        )

        volume_confirm = (
            (
                fast.get("relative_volume")
                or 0
            )
            >= 1.3
        )

        rsi_weak = (
            fast.get("rsi") is not None
            and fast["rsi"] < 45
        )

        negative_score = 0

        if fast_negative:
            negative_score += 1
            evidence.append(
                "1m momentum weakening"
            )

        if confirm_negative:
            negative_score += 2
            evidence.append(
                "5m trend negative"
            )

        if breakdown:
            negative_score += 2
            evidence.append(
                "price breakdown"
            )

        if volume_confirm:
            negative_score += 1
            evidence.append(
                "selling volume confirmation"
            )

        if rsi_weak:
            negative_score += 1
            evidence.append(
                "momentum weak"
            )

        if (
            breakdown
            and confirm_negative
            and negative_score >= 5
        ):
            signal_type = "CONFIRMED_SELL"
            severity = 85
            confirmed = True

        elif negative_score >= 3:
            signal_type = "EARLY_WARNING"
            severity = 55
            confirmed = False

        elif (
            pnl_pct is not None
            and pnl_pct >= 4
            and fast_negative
        ):
            signal_type = "PROTECT_PROFIT"
            severity = 65
            confirmed = False

    if signal_type is None:
        signal_type = "HOLD"
        severity = 10
        confirmed = False

    return {
        "signal_type": signal_type,
        "severity": severity,
        "confirmed": confirmed,
        "price": price,
        "pnl_pct": pnl_pct,
        "evidence": evidence,
    }


def insert_signal(
    ticker,
    signal_type,
    severity,
    price,
    reason,
    confirmed=False,
    entry_low=None,
    entry_high=None,
    stop_loss=None,
    target_1=None,
    target_2=None,
    risk_reward=None,
    confidence=None,
    expires_at=None,
    user_id=None,
    portfolio_id=None,
):
    payload = {
        "ticker": clean_ticker(ticker),
        "signal_type": signal_type,
        "severity": severity,
        "price": price,
        "entry_low": entry_low,
        "entry_high": entry_high,
        "stop_loss": stop_loss,
        "target_1": target_1,
        "target_2": target_2,
        "risk_reward": risk_reward,
        "confidence": confidence,
        "reason": reason,
        "confirmed": confirmed,
        "created_at": now_iso(),
        "expires_at": expires_at,
        "active": True,
    }

    if user_id is not None:
        payload["user_id"] = user_id

    if portfolio_id is not None:
        payload["portfolio_id"] = portfolio_id

    rows = supabase_request(
        "POST",
        "hanz_signals",
        payload,
        prefer="return=representation",
    )

    if rows:
        return rows[0]

    return None


def make_dedupe_key(
    ticker,
    alert_type,
    user_id=None,
    portfolio_id=None,
):
    bucket = int(
        utc_now().timestamp()
        // ALERT_COOLDOWN_SECONDS
    )

    owner = user_id or "SHARED"
    position = portfolio_id if portfolio_id is not None else "MARKET"

    return (
        f"{owner}:"
        f"{position}:"
        f"{clean_ticker(ticker)}:"
        f"{alert_type}:"
        f"{bucket}"
    )


def queue_alert(
    ticker,
    alert_type,
    priority,
    title,
    message,
    signal_id=None,
    user_id=None,
    portfolio_id=None,
):
    dedupe_key = make_dedupe_key(
        ticker,
        alert_type,
        user_id=user_id,
        portfolio_id=portfolio_id,
    )

    payload = {
        "ticker": clean_ticker(ticker),
        "alert_type": alert_type,
        "priority": priority,
        "title": title,
        "message": message,
        "signal_id": signal_id,
        "status": "PENDING",
        "dedupe_key": dedupe_key,
        "created_at": now_iso(),
    }

    if user_id is not None:
        payload["user_id"] = user_id

    if portfolio_id is not None:
        payload["portfolio_id"] = portfolio_id

    try:
        supabase_request(
            "POST",
            "hanz_alerts",
            payload,
            prefer="return=minimal",
        )

        print(
            f"ALERT QUEUED: {title} "
            f"user={user_id or 'SHARED'} "
            f"portfolio_id={portfolio_id or 'MARKET'}",
            flush=True,
        )

        send_selective_push(
            ticker=ticker,
            alert_type=alert_type,
            title=title,
            message=message,
            user_id=user_id,
            portfolio_id=portfolio_id,
        )

    except Exception as exc:
        if "409" in str(exc):
            print(
                f"Alert suppressed duplicate: "
                f"{dedupe_key}",
                flush=True,
            )
        else:
            raise



def jakarta_date_string():
    return utc_now().astimezone(JAKARTA_TZ).date().isoformat()


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
            f"FCM init unavailable: {exc}",
            flush=True,
        )
        return None


def push_event_key(
    *,
    ticker,
    alert_type,
    user_id=None,
    portfolio_id=None,
):
    ticker = clean_ticker(ticker)
    day = jakarta_date_string()

    if alert_type == "CONFIRMED_BUY":
        # One shared confirmed BUY push per ticker per IDX trading day.
        return f"SHARED:{ticker}:{alert_type}:{day}"

    if alert_type == "PROTECT_PROFIT":
        # At most one protect-profit push per position per trading day.
        return (
            f"{user_id}:{portfolio_id}:"
            f"{alert_type}:{day}"
        )

    # STOP_LOSS / CONFIRMED_SELL / TRAILING_ACTIVATED
    # are one-time events per portfolio row.
    return f"{user_id}:{portfolio_id}:{alert_type}"


def reserve_push_event(
    *,
    event_key,
    ticker,
    alert_type,
    user_id=None,
    portfolio_id=None,
):
    payload = {
        "event_key": event_key,
        "ticker": clean_ticker(ticker),
        "alert_type": alert_type,
        "status": "PENDING",
        "created_at": now_iso(),
    }

    if user_id is not None:
        payload["user_id"] = user_id

    if portfolio_id is not None:
        payload["portfolio_id"] = portfolio_id

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


def get_push_installation_ids(user_id=None):
    query = (
        "hanz_push_devices"
        "?enabled=eq.true"
        "&select=installation_id"
    )

    if user_id is not None:
        encoded_user = urllib.parse.quote(
            str(user_id),
            safe="",
        )
        query += f"&user_id=eq.{encoded_user}"

    rows = supabase_request(
        "GET",
        query,
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
    user_id=None,
    portfolio_id=None,
):
    if alert_type not in PUSH_ALERT_TYPES:
        return

    app = firebase_app()

    if app is None or messaging is None:
        print(
            f"PUSH SKIPPED: Firebase not configured "
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
            f"PUSH SUPPRESSED duplicate: {event_key}",
            flush=True,
        )
        return

    try:
        # Shared confirmed BUY -> every enabled HANZ device.
        # Portfolio alerts -> only that user's enabled devices.
        target_user = (
            None
            if alert_type == "CONFIRMED_BUY"
            else user_id
        )

        installation_ids = get_push_installation_ids(
            target_user
        )

        if not installation_ids:
            finish_push_event(
                event_key,
                "NO_DEVICE",
            )
            print(
                f"PUSH NO DEVICE: {event_key}",
                flush=True,
            )
            return

        messages = []

        for fid in installation_ids:
            data = {
                "title": str(title),
                "body": str(message),
                "message": str(message),
                "ticker": clean_ticker(ticker),
                "alert_type": str(alert_type),
                "url": PUSH_DASHBOARD_URL,
                "dedupe_key": event_key,
            }

            if portfolio_id is not None:
                data["portfolio_id"] = str(portfolio_id)

            messages.append(
                messaging.Message(
                    data=data,
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
            f"PUSH SENT: {event_key} "
            f"success={response.success_count} "
            f"failed={response.failure_count}",
            flush=True,
        )

    except Exception as exc:
        release_failed_push_event(event_key)

        print(
            f"PUSH FAILED: {event_key} — {exc}",
            flush=True,
        )



def update_fast_health(
    *,
    last_market_bar_at=None,
    data_age_seconds_value=None,
    data_status="FRESH",
    symbols_monitored=0,
    error=None,
):
    payload = {
        "id": FAST_STATE_ID,
        "last_scan_at": now_iso(),
        "last_market_bar_at": last_market_bar_at,
        "data_age_seconds": data_age_seconds_value,
        "data_status": data_status,
        "symbols_monitored": symbols_monitored,
        "last_error": error,
        "updated_at": now_iso(),
    }

    supabase_request(
        "POST",
        "hanz_fast_health?on_conflict=id",
        payload,
        prefer=(
            "resolution=merge-duplicates,"
            "return=minimal"
        ),
    )


def get_symbol_context(ticker):
    symbol, fast_df, fast_latency = (
        download_data(
            ticker,
            INTRADAY_INTERVAL,
            INTRADAY_PERIOD,
        )
    )

    _, confirm_df, confirm_latency = (
        download_data(
            ticker,
            CONFIRM_INTERVAL,
            CONFIRM_PERIOD,
        )
    )

    age = data_age_seconds(fast_df)

    last_bar = last_timestamp_utc(
        fast_df
    ).isoformat()

    fast_metrics = calculate_metrics(
        fast_df
    )

    confirm_metrics = calculate_metrics(
        confirm_df
    )

    return {
        "symbol": symbol,
        "fast": fast_metrics,
        "confirm": confirm_metrics,
        "age_seconds": age,
        "last_bar": last_bar,
        "latency": round(
            fast_latency + confirm_latency,
            3,
        ),
    }



def trend_label(metrics):
    ema9 = safe_float(metrics.get("ema9"))
    ema21 = safe_float(metrics.get("ema21"))

    if ema9 is None or ema21 is None:
        return "UNKNOWN"

    if ema9 > ema21:
        return "BULLISH"

    if ema9 < ema21:
        return "BEARISH"

    return "FLAT"


def upsert_signal_monitor(
    *,
    ticker,
    state,
    price=None,
    fast_trend=None,
    confirm_trend=None,
    score=None,
    confidence=None,
    rsi_1m=None,
    rsi_5m=None,
    relative_volume=None,
    confirmation_price=None,
    entry_low=None,
    entry_high=None,
    invalidation_price=None,
    distance_to_confirm_pct=None,
    last_market_bar_at=None,
    data_age_seconds_value=None,
    data_status="FRESH",
    evidence=None,
    source="SLOW_WATCHLIST",
    scout_score=None,
    expires_at=None,
):
    payload = {
        "ticker": clean_ticker(ticker),
        "state": state,
        "price": price,
        "fast_trend": fast_trend,
        "confirm_trend": confirm_trend,
        "score": score,
        "confidence": confidence,
        "rsi_1m": rsi_1m,
        "rsi_5m": rsi_5m,
        "relative_volume": relative_volume,
        "confirmation_price": confirmation_price,
        "entry_low": entry_low,
        "entry_high": entry_high,
        "invalidation_price": invalidation_price,
        "distance_to_confirm_pct": distance_to_confirm_pct,
        "last_market_bar_at": last_market_bar_at,
        "data_age_seconds": data_age_seconds_value,
        "data_status": data_status,
        "evidence": evidence,
        "source": source,
        "scout_score": scout_score,
        "expires_at": expires_at,
        "updated_at": now_iso(),
    }

    supabase_request(
        "POST",
        "hanz_signal_monitor?on_conflict=ticker",
        payload,
        prefer=(
            "resolution=merge-duplicates,"
            "return=minimal"
        ),
    )


def delete_stale_signal_monitor_rows(active_tickers):
    normalized = sorted({
        clean_ticker(ticker)
        for ticker in active_tickers
        if ticker
    })

    try:
        rows = supabase_request(
            "GET",
            "hanz_signal_monitor"
            "?source=eq.SLOW_WATCHLIST"
            "&select=ticker",
        ) or []

        for row in rows:
            ticker = clean_ticker(
                row.get("ticker")
            )

            if ticker in normalized:
                continue

            encoded = urllib.parse.quote(
                ticker,
                safe="",
            )

            supabase_request(
                "DELETE",
                "hanz_signal_monitor"
                f"?ticker=eq.{encoded}"
                "&source=eq.SLOW_WATCHLIST",
                prefer="return=minimal",
            )

    except Exception as exc:
        print(
            f"Signal monitor stale cleanup skipped: {exc}",
            flush=True,
        )



def monitor_portfolio(positions, context_cache=None):
    monitored = 0
    context_cache = context_cache if context_cache is not None else {}

    for position in positions:
        ticker = position.get("ticker")
        user_id = position.get("user_id")
        portfolio_id = position.get("id")

        if not ticker:
            continue

        try:
            cache_key = clean_ticker(ticker)

            if cache_key not in context_cache:
                context_cache[cache_key] = get_symbol_context(ticker)

            ctx = context_cache[cache_key]
            monitored += 1

            if ctx["age_seconds"] > MAX_DATA_AGE_SECONDS:
                print(
                    f"{ticker}: portfolio scan blocked — stale data "
                    f"{ctx['age_seconds']} sec "
                    f"user={user_id} portfolio_id={portfolio_id}",
                    flush=True,
                )
                continue

            position = apply_auto_trailing(
                position,
                ctx["fast"],
            )

            result = portfolio_signal(
                ctx["fast"],
                ctx["confirm"],
                position,
            )

            if not result:
                continue

            signal_type = result["signal_type"]

            # Persist latest per-position engine state without auto-closing
            # the trade. The user closes the position after actual execution.
            if portfolio_id is not None:
                current_signal = str(position.get("signal") or "")
                if current_signal != signal_type:
                    update_portfolio_row(
                        portfolio_id,
                        {"signal": signal_type},
                    )
                    position["signal"] = signal_type

            if signal_type == "HOLD":
                print(
                    f"{ticker}: HOLD "
                    f"user={user_id} portfolio_id={portfolio_id}",
                    flush=True,
                )
                continue

            reason = "; ".join(result["evidence"]) or signal_type

            signal = insert_signal(
                ticker=ticker,
                signal_type=signal_type,
                severity=result["severity"],
                price=result["price"],
                reason=reason,
                confirmed=result["confirmed"],
                stop_loss=safe_float(position.get("stop_loss")),
                target_1=safe_float(position.get("target_1")),
                target_2=safe_float(position.get("target_2")),
                user_id=user_id,
                portfolio_id=portfolio_id,
            )

            signal_id = signal.get("id") if signal else None

            pnl_text = ""
            if result["pnl_pct"] is not None:
                pnl_text = f" | P/L {result['pnl_pct']:.2f}%"

            trailing_text = ""
            trailing_stop = safe_float(position.get("trailing_stop"))
            if trailing_stop is not None:
                trailing_text = f" | Trail {trailing_stop:.2f}"

            title = f"{clean_ticker(ticker)} — {signal_type}"

            message = (
                f"Price {result['price']:.2f}"
                f"{pnl_text}{trailing_text}. "
                f"{reason}"
            )

            queue_alert(
                ticker=ticker,
                alert_type=signal_type,
                priority=result["severity"],
                title=title,
                message=message,
                signal_id=signal_id,
                user_id=user_id,
                portfolio_id=portfolio_id,
            )

        except Exception as exc:
            print(
                f"Portfolio monitor {ticker} failed: {exc} "
                f"user={user_id} portfolio_id={portfolio_id}",
                flush=True,
            )

    return monitored



def fetch_scout_universe():
    rows = supabase_request(
        "GET",
        "hanz_scout_universe"
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

    return tickers


def scout_cursor():
    try:
        return int(
            Path(
                FAST_SCOUT_CURSOR_FILE
            ).read_text(
                encoding="utf-8"
            ).strip()
            or 0
        )
    except Exception:
        return 0


def save_scout_cursor(value):
    try:
        Path(
            FAST_SCOUT_CURSOR_FILE
        ).write_text(
            str(int(value)),
            encoding="utf-8",
        )
    except Exception:
        pass


def scout_batch(universe, excluded):
    candidates = [
        ticker
        for ticker in universe
        if ticker not in excluded
    ]

    if not candidates:
        return []

    batch_size = max(
        1,
        min(
            FAST_SCOUT_BATCH_SIZE,
            len(candidates),
        ),
    )

    start = scout_cursor() % len(
        candidates
    )

    batch = []

    for offset in range(batch_size):
        batch.append(
            candidates[
                (start + offset)
                % len(candidates)
            ]
        )

    save_scout_cursor(
        (start + batch_size)
        % len(candidates)
    )

    return batch


def scout_metrics(frame):
    metrics = calculate_metrics(frame)

    price = safe_float(
        metrics.get("price")
    )

    open_price = safe_float(
        metrics.get("open")
    )

    move_1m_pct = None

    if (
        price is not None
        and open_price is not None
        and open_price > 0
    ):
        move_1m_pct = (
            (price - open_price)
            / open_price
            * 100
        )

    move_5m_pct = None

    if (
        price is not None
        and len(frame) >= 6
    ):
        base = safe_float(
            frame["Close"].iloc[-6]
        )

        if (
            base is not None
            and base > 0
        ):
            move_5m_pct = (
                (price - base)
                / base
                * 100
            )

    metrics["move_1m_pct"] = (
        move_1m_pct
    )

    metrics["move_5m_pct"] = (
        move_5m_pct
    )

    return metrics


def fast_scout_score(metrics):
    score = 0
    evidence = []

    price = safe_float(
        metrics.get("price")
    )

    prior_high = safe_float(
        metrics.get("prior_high20")
    )

    breakout = (
        price is not None
        and prior_high is not None
        and price > prior_high
    )

    if breakout:
        score += 3
        evidence.append(
            "1m breakout above prior 20-bar high"
        )

    rvol = safe_float(
        metrics.get("relative_volume")
    ) or 0

    if rvol >= 2.0:
        score += 3
        evidence.append(
            f"RVOL surge {rvol:.2f}x"
        )
    elif rvol >= 1.5:
        score += 2
        evidence.append(
            f"RVOL strong {rvol:.2f}x"
        )
    elif rvol >= 1.25:
        score += 1
        evidence.append(
            f"RVOL improving {rvol:.2f}x"
        )

    ema9 = safe_float(
        metrics.get("ema9")
    )

    ema21 = safe_float(
        metrics.get("ema21")
    )

    if (
        ema9 is not None
        and ema21 is not None
        and ema9 > ema21
    ):
        score += 1
        evidence.append(
            "1m EMA9 above EMA21"
        )

    rsi_value = safe_float(
        metrics.get("rsi")
    )

    if (
        rsi_value is not None
        and 55 <= rsi_value <= 82
    ):
        score += 1
        evidence.append(
            f"1m RSI {rsi_value:.1f}"
        )

    move_5m = safe_float(
        metrics.get("move_5m_pct")
    )

    if (
        move_5m is not None
        and move_5m >= 0.8
    ):
        score += 1
        evidence.append(
            f"5m acceleration +{move_5m:.2f}%"
        )

    return {
        "score": score,
        "evidence": evidence,
        "breakout": breakout,
    }


def scout_expiry_iso():
    return (
        utc_now()
        + pd.Timedelta(
            minutes=
            FAST_SCOUT_CANDIDATE_MINUTES
        ).to_pytimedelta()
    ).isoformat()


def fetch_active_scout_candidates():
    now_encoded = urllib.parse.quote(
        now_iso(),
        safe="",
    )

    return supabase_request(
        "GET",
        "hanz_signal_monitor"
        "?source=eq.FAST_SCOUT"
        f"&expires_at=gt.{now_encoded}"
        "&select=*",
    ) or []


def cleanup_expired_scout_candidates():
    now_encoded = urllib.parse.quote(
        now_iso(),
        safe="",
    )

    try:
        supabase_request(
            "DELETE",
            "hanz_signal_monitor"
            "?source=eq.FAST_SCOUT"
            f"&expires_at=lt.{now_encoded}",
            prefer="return=minimal",
        )
    except Exception as exc:
        print(
            f"Fast Scout cleanup skipped: {exc}",
            flush=True,
        )


def discover_fast_scout_candidates(
    universe,
    watchlist,
    portfolio,
):
    if not FAST_SCOUT_ENABLED:
        return 0

    excluded = {
        clean_ticker(
            row.get("ticker")
        )
        for row in (
            list(watchlist)
            + list(portfolio)
        )
        if row.get("ticker")
    }

    active = fetch_active_scout_candidates()

    excluded.update({
        clean_ticker(
            row.get("ticker")
        )
        for row in active
        if row.get("ticker")
    })

    batch = scout_batch(
        universe,
        excluded,
    )

    if not batch:
        return 0

    print(
        "FAST SCOUT batch: "
        + ", ".join(batch),
        flush=True,
    )

    discovered = 0

    for ticker in batch:
        try:
            _, frame, _ = download_data(
                ticker,
                interval=INTRADAY_INTERVAL,
                period=INTRADAY_PERIOD,
            )

            age = data_age_seconds(
                frame
            )

            if age > MAX_DATA_AGE_SECONDS:
                continue

            metrics = scout_metrics(
                frame
            )

            result = fast_scout_score(
                metrics
            )

            # Surprise detector is intentionally strict:
            # breakout is mandatory and total score must be high.
            if not (
                result["breakout"]
                and result["score"]
                >= FAST_SCOUT_MIN_SCORE
            ):
                continue

            price = safe_float(
                metrics.get("price")
            )

            prior_high = safe_float(
                metrics.get("prior_high20")
            )

            evidence = "; ".join(
                result["evidence"]
            )

            upsert_signal_monitor(
                ticker=ticker,
                state="SURPRISE_WATCH",
                price=price,
                fast_trend=trend_label(
                    metrics
                ),
                confirm_trend="PENDING",
                score=None,
                confidence=None,
                rsi_1m=metrics.get("rsi"),
                rsi_5m=None,
                relative_volume=(
                    metrics.get(
                        "relative_volume"
                    )
                ),
                confirmation_price=prior_high,
                entry_low=price,
                entry_high=price,
                invalidation_price=(
                    metrics.get(
                        "prior_low20"
                    )
                ),
                distance_to_confirm_pct=0,
                last_market_bar_at=(
                    last_timestamp_utc(
                        frame
                    ).isoformat()
                ),
                data_age_seconds_value=age,
                data_status="FRESH",
                evidence=evidence,
                source="FAST_SCOUT",
                scout_score=result["score"],
                expires_at=scout_expiry_iso(),
            )

            discovered += 1

            print(
                f"FAST SCOUT discovered "
                f"{ticker} score "
                f"{result['score']}/9",
                flush=True,
            )

        except Exception as exc:
            print(
                f"FAST SCOUT {ticker} skipped: "
                f"{exc}",
                flush=True,
            )

    return discovered


def confirm_fast_scout_candidates(
    context_cache=None,
):
    context_cache = (
        context_cache
        if context_cache is not None
        else {}
    )

    candidates = (
        fetch_active_scout_candidates()
    )

    confirmed_count = 0

    for candidate in candidates:
        ticker = candidate.get(
            "ticker"
        )

        if not ticker:
            continue

        previous_state = str(
            candidate.get("state")
            or ""
        ).upper()

        try:
            cache_key = clean_ticker(
                ticker
            )

            if (
                cache_key
                not in context_cache
            ):
                context_cache[
                    cache_key
                ] = get_symbol_context(
                    ticker
                )

            ctx = context_cache[
                cache_key
            ]

            fast = ctx["fast"]
            confirm = ctx["confirm"]

            watch = {
                "confirmation_price":
                    candidate.get(
                        "confirmation_price"
                    ),
                "entry_zone_low":
                    candidate.get(
                        "entry_low"
                    ),
                "entry_zone_high":
                    candidate.get(
                        "entry_high"
                    ),
                "invalidation_price":
                    candidate.get(
                        "invalidation_price"
                    ),
            }

            result = buy_confirmation(
                fast,
                confirm,
                watch,
            )

            if not result:
                continue

            if (
                ctx["age_seconds"]
                > MAX_DATA_AGE_SECONDS
            ):
                state = "STALE_DATA"
                data_status = "STALE"
            elif result["confirmed"]:
                state = "CONFIRMED_BUY"
                data_status = "FRESH"
            else:
                state = "FAST_CONFIRMING"
                data_status = "FRESH"

            confidence = min(
                100,
                result["score"]
                / 9
                * 100,
            )

            evidence = (
                "; ".join(
                    result["evidence"]
                )
                or candidate.get(
                    "evidence"
                )
                or "Fast Scout confirmation pending"
            )

            upsert_signal_monitor(
                ticker=ticker,
                state=state,
                price=result["price"],
                fast_trend=trend_label(
                    fast
                ),
                confirm_trend=trend_label(
                    confirm
                ),
                score=result["score"],
                confidence=round(
                    confidence,
                    1,
                ),
                rsi_1m=fast.get("rsi"),
                rsi_5m=confirm.get("rsi"),
                relative_volume=(
                    fast.get(
                        "relative_volume"
                    )
                ),
                confirmation_price=(
                    candidate.get(
                        "confirmation_price"
                    )
                ),
                entry_low=(
                    candidate.get(
                        "entry_low"
                    )
                ),
                entry_high=(
                    candidate.get(
                        "entry_high"
                    )
                ),
                invalidation_price=(
                    candidate.get(
                        "invalidation_price"
                    )
                ),
                distance_to_confirm_pct=0,
                last_market_bar_at=(
                    ctx["last_bar"]
                ),
                data_age_seconds_value=(
                    ctx["age_seconds"]
                ),
                data_status=data_status,
                evidence=evidence,
                source="FAST_SCOUT",
                scout_score=(
                    candidate.get(
                        "scout_score"
                    )
                ),
                expires_at=(
                    candidate.get(
                        "expires_at"
                    )
                ),
            )

            if (
                state
                != "CONFIRMED_BUY"
            ):
                print(
                    f"{ticker}: "
                    f"FAST_CONFIRMING "
                    f"{result['score']}/9",
                    flush=True,
                )
                continue

            confirmed_count += 1

            # Only create a new signal/alert on state transition.
            if (
                previous_state
                == "CONFIRMED_BUY"
            ):
                continue

            signal = insert_signal(
                ticker=ticker,
                signal_type=(
                    "CONFIRMED_BUY"
                ),
                severity=85,
                price=result["price"],
                reason=(
                    "FAST SCOUT: "
                    + evidence
                ),
                confirmed=True,
                entry_low=(
                    result["entry_low"]
                ),
                entry_high=(
                    result["entry_high"]
                ),
                stop_loss=(
                    result["stop_loss"]
                ),
                target_1=(
                    result["target_1"]
                ),
                target_2=(
                    result["target_2"]
                ),
                risk_reward=(
                    result["risk_reward"]
                ),
                confidence=round(
                    confidence,
                    1,
                ),
                expires_at=(
                    candidate.get(
                        "expires_at"
                    )
                ),
            )

            signal_id = (
                signal.get("id")
                if signal
                else None
            )

            title = (
                f"{clean_ticker(ticker)} "
                f"— CONFIRMED BUY"
            )

            message = (
                f"FAST SCOUT confirmed. "
                f"Price "
                f"{result['price']:.2f} | "
                f"Score "
                f"{result['score']}/9 | "
                f"{evidence}"
            )

            queue_alert(
                ticker=ticker,
                alert_type=(
                    "CONFIRMED_BUY"
                ),
                priority=85,
                title=title,
                message=message,
                signal_id=signal_id,
            )

            print(
                f"FAST SCOUT CONFIRMED BUY: "
                f"{ticker}",
                flush=True,
            )

        except Exception as exc:
            print(
                f"FAST SCOUT confirm "
                f"{ticker} failed: {exc}",
                flush=True,
            )

    return confirmed_count



def monitor_watchlist(watchlist, context_cache=None):
    monitored = 0
    context_cache = context_cache if context_cache is not None else {}

    active_tickers = [
        watch.get("ticker")
        for watch in watchlist
        if watch.get("ticker")
    ]

    for watch in watchlist:
        ticker = watch.get("ticker")

        if not ticker:
            continue

        try:
            cache_key = clean_ticker(ticker)

            if cache_key not in context_cache:
                context_cache[cache_key] = get_symbol_context(ticker)

            ctx = context_cache[cache_key]
            monitored += 1

            result = buy_confirmation(
                ctx["fast"],
                ctx["confirm"],
                watch,
            )

            if not result:
                upsert_signal_monitor(
                    ticker=ticker,
                    state="NO_DATA",
                    data_status="NO_DATA",
                    last_market_bar_at=ctx.get("last_bar"),
                    data_age_seconds_value=ctx.get("age_seconds"),
                )
                continue

            fast = ctx["fast"]
            confirm = ctx["confirm"]

            confirmation_price = safe_float(
                watch.get("confirmation_price")
            )

            distance_to_confirm_pct = None

            if (
                confirmation_price is not None
                and result["price"] is not None
                and result["price"] > 0
            ):
                distance_to_confirm_pct = (
                    (
                        confirmation_price
                        - result["price"]
                    )
                    / result["price"]
                    * 100
                )

            confidence = min(
                100,
                result["score"]
                / 9
                * 100,
            )

            if (
                ctx["age_seconds"]
                > MAX_DATA_AGE_SECONDS
            ):
                state = "STALE_DATA"
                data_status = "STALE"

            elif result["confirmed"]:
                state = "CONFIRMED_BUY"
                data_status = "FRESH"

            elif result["early_watch"]:
                state = "EARLY_WATCH"
                data_status = "FRESH"

            else:
                state = "WAIT_CONFIRM"
                data_status = "FRESH"

            evidence = (
                "; ".join(result["evidence"])
                or "waiting for confirmation"
            )

            upsert_signal_monitor(
                ticker=ticker,
                state=state,
                price=result["price"],
                fast_trend=trend_label(fast),
                confirm_trend=trend_label(confirm),
                score=result["score"],
                confidence=round(confidence, 1),
                rsi_1m=fast.get("rsi"),
                rsi_5m=confirm.get("rsi"),
                relative_volume=fast.get("relative_volume"),
                confirmation_price=confirmation_price,
                entry_low=result["entry_low"],
                entry_high=result["entry_high"],
                invalidation_price=safe_float(
                    watch.get("invalidation_price")
                ),
                distance_to_confirm_pct=(
                    round(distance_to_confirm_pct, 3)
                    if distance_to_confirm_pct is not None
                    else None
                ),
                last_market_bar_at=ctx["last_bar"],
                data_age_seconds_value=ctx["age_seconds"],
                data_status=data_status,
                evidence=evidence,
            )

            if state == "STALE_DATA":
                print(
                    f"{ticker}: BUY scan blocked "
                    f"— stale data "
                    f"{ctx['age_seconds']} sec",
                    flush=True,
                )
                continue

            if state == "WAIT_CONFIRM":
                print(
                    f"{ticker}: WAIT_CONFIRM "
                    f"score {result['score']}/9",
                    flush=True,
                )
                continue

            if state == "CONFIRMED_BUY":
                signal_type = "CONFIRMED_BUY"
                severity = 70
                confirmed = True

            else:
                signal_type = "EARLY_WATCH"
                severity = 35
                confirmed = False

            signal = insert_signal(
                ticker=ticker,
                signal_type=signal_type,
                severity=severity,
                price=result["price"],
                reason=evidence,
                confirmed=confirmed,
                entry_low=result["entry_low"],
                entry_high=result["entry_high"],
                stop_loss=result["stop_loss"],
                target_1=result["target_1"],
                target_2=result["target_2"],
                risk_reward=result["risk_reward"],
                confidence=round(
                    confidence,
                    1,
                ),
                expires_at=watch.get(
                    "expires_at"
                ),
            )

            signal_id = (
                signal.get("id")
                if signal
                else None
            )

            title = (
                f"{clean_ticker(ticker)} "
                f"— {signal_type}"
            )

            if confirmed:
                message = (
                    f"Price "
                    f"{result['price']:.2f}. "
                    f"Confirmation score "
                    f"{result['score']}/9. "
                    f"{evidence}. "
                    f"SL "
                    f"{result['stop_loss']}"
                )

            else:
                message = (
                    f"Setup developing. "
                    f"Price "
                    f"{result['price']:.2f}. "
                    f"Waiting confirmation "
                    f"{confirmation_price}. "
                    f"{evidence}"
                )

            queue_alert(
                ticker=ticker,
                alert_type=signal_type,
                priority=severity,
                title=title,
                message=message,
                signal_id=signal_id,
            )

        except Exception as exc:
            print(
                f"Watchlist monitor "
                f"{ticker} failed: {exc}",
                flush=True,
            )

            try:
                upsert_signal_monitor(
                    ticker=ticker,
                    state="ERROR",
                    data_status="ERROR",
                    evidence=str(exc),
                )
            except Exception:
                pass

    delete_stale_signal_monitor_rows(active_tickers)

    return monitored



def run_fast_cycle():
    print(
        "\n========== HANZ FAST CYCLE ==========",
        flush=True,
    )

    portfolio = fetch_portfolio()
    watchlist = fetch_watchlist()

    try:
        scout_universe = (
            fetch_scout_universe()
            if FAST_SCOUT_ENABLED
            else []
        )
    except Exception as exc:
        print(
            f"FAST SCOUT universe unavailable: {exc}",
            flush=True,
        )
        scout_universe = []

    print(
        f"Portfolio positions: "
        f"{len(portfolio)}",
        flush=True,
    )

    print(
        f"Watchlist symbols: "
        f"{len(watchlist)}",
        flush=True,
    )

    print(
        f"Fast Scout universe: "
        f"{len(scout_universe)}",
        flush=True,
    )

    context_cache = {}

    portfolio_count = monitor_portfolio(
        portfolio,
        context_cache=context_cache,
    )

    watch_count = monitor_watchlist(
        watchlist,
        context_cache=context_cache,
    )

    cleanup_expired_scout_candidates()

    scout_discovered = (
        discover_fast_scout_candidates(
            scout_universe,
            watchlist,
            portfolio,
        )
        if scout_universe
        else 0
    )

    scout_confirmed = (
        confirm_fast_scout_candidates(
            context_cache=context_cache,
        )
        if FAST_SCOUT_ENABLED
        else 0
    )

    total = (
        portfolio_count
        + watch_count
        + scout_discovered
        + scout_confirmed
    )

    update_fast_health(
        data_status="FRESH",
        symbols_monitored=total,
        error=None,
    )

    print(
        f"FAST cycle complete. "
        f"Symbols monitored: {total}",
        flush=True,
    )


def main():
    print(
        "HANZ FAST Trading Engine started.",
        flush=True,
    )

    print(
        f"Run once mode: {RUN_ONCE}",
        flush=True,
    )

    print(
        f"Fast Scout enabled: "
        f"{FAST_SCOUT_ENABLED} | "
        f"batch={FAST_SCOUT_BATCH_SIZE} | "
        f"min_score={FAST_SCOUT_MIN_SCORE}",
        flush=True,
    )

    print(
        f"Fast interval: "
        f"{FAST_INTERVAL} seconds",
        flush=True,
    )

    print(
        f"Fast timeframe: "
        f"{INTRADAY_INTERVAL}",
        flush=True,
    )

    print(
        f"Confirmation timeframe: "
        f"{CONFIRM_INTERVAL}",
        flush=True,
    )

    while True:
        try:
            run_fast_cycle()

        except Exception as exc:
            print(
                f"HANZ FAST cycle failed: "
                f"{exc}",
                flush=True,
            )

            try:
                update_fast_health(
                    data_status="DEGRADED",
                    symbols_monitored=0,
                    error=str(exc),
                )

            except Exception as health_exc:
                print(
                    f"FAST health update failed: "
                    f"{health_exc}",
                    flush=True,
                )

        if RUN_ONCE:
            print(
                "HANZ FAST controlled test "
                "completed. Exiting.",
                flush=True,
            )

            break

        print(
            f"FAST engine sleeping "
            f"{FAST_INTERVAL} seconds...",
            flush=True,
        )

        time.sleep(
            FAST_INTERVAL
        )


if __name__ == "__main__":
    main()
