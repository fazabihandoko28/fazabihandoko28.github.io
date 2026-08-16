import json
import math
import os
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

import pandas as pd
import yfinance as yf


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
        update_portfolio_row(portfolio_id, updates)
        position.update(updates)

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

    except Exception as exc:
        if "409" in str(exc):
            print(
                f"Alert suppressed duplicate: "
                f"{dedupe_key}",
                flush=True,
            )
        else:
            raise


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


def monitor_watchlist(watchlist, context_cache=None):
    monitored = 0
    context_cache = context_cache if context_cache is not None else {}

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

            if (
                ctx["age_seconds"]
                > MAX_DATA_AGE_SECONDS
            ):
                print(
                    f"{ticker}: BUY scan blocked "
                    f"— stale data "
                    f"{ctx['age_seconds']} sec",
                    flush=True,
                )

                continue

            result = buy_confirmation(
                ctx["fast"],
                ctx["confirm"],
                watch,
            )

            if not result:
                continue

            if result["confirmed"]:
                signal_type = "CONFIRMED_BUY"
                severity = 70
                confirmed = True

            elif result["early_watch"]:
                signal_type = "EARLY_WATCH"
                severity = 35
                confirmed = False

            else:
                print(
                    f"{ticker}: no actionable setup",
                    flush=True,
                )
                continue

            evidence = "; ".join(
                result["evidence"]
            )

            confidence = min(
                100,
                result["score"]
                / 9
                * 100,
            )

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
                confirmation_price = (
                    watch.get(
                        "confirmation_price"
                    )
                )

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

    return monitored


def run_fast_cycle():
    print(
        "\n========== HANZ FAST CYCLE ==========",
        flush=True,
    )

    portfolio = fetch_portfolio()
    watchlist = fetch_watchlist()

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

    context_cache = {}

    portfolio_count = monitor_portfolio(
        portfolio,
        context_cache=context_cache,
    )

    watch_count = monitor_watchlist(
        watchlist,
        context_cache=context_cache,
    )

    total = (
        portfolio_count
        + watch_count
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
