
import json
import math
import os
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

import pandas as pd
import yfinance as yf


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

    print(
        "SWING cycle complete: "
        + json.dumps(counts),
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
        f"Cycle={SWING_INTERVAL}s",
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
