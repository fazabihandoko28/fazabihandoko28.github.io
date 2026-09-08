import json
from pathlib import Path

import yfinance as yf

from .swing_trading_engine import idx_market_session, jakarta_now


OUT = Path("docs/dashboard/swing/ihsg-snapshot.json")
SYMBOL = "^JKSE"


def _last_numeric(series):
    if series is None:
        return None
    try:
        clean = series.dropna()
        if len(clean):
            return float(clean.iloc[-1])
    except Exception:
        return None
    return None


def _read_existing():
    try:
        if OUT.exists():
            return json.loads(OUT.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _date_of_index(value):
    try:
        return value.tz_convert("Asia/Jakarta").date()
    except Exception:
        try:
            return value.date()
        except Exception:
            return None


def fetch_ihsg():
    now = jakarta_now()
    market = idx_market_session()
    state = str(market.get("state") or "")
    is_live = bool(market.get("is_trading_day")) and state in {"SESSION_1", "SESSION_2"}

    ticker = yf.Ticker(SYMBOL)
    daily = ticker.history(period="10d", interval="1d", auto_adjust=False)
    if daily is None or daily.empty or "Close" not in daily:
        raise RuntimeError("IHSG daily history unavailable")

    closes = daily["Close"].dropna()
    if closes.empty:
        raise RuntimeError("IHSG daily close unavailable")

    daily_rows = [(idx, float(value)) for idx, value in closes.items()]
    latest_idx, latest_close = daily_rows[-1]
    latest_date = _date_of_index(latest_idx)

    price = latest_close
    quote_at = latest_idx.isoformat() if hasattr(latest_idx, "isoformat") else None
    quote_type = "LAST_CLOSE"

    # During an active IDX session prefer the freshest intraday quote.
    # Outside market hours, deliberately keep the latest completed daily close
    # so the dashboard remains useful as the baseline for the next session.
    if is_live:
        for interval, period in (("1m", "1d"), ("2m", "5d"), ("5m", "5d")):
            try:
                intraday = ticker.history(
                    period=period,
                    interval=interval,
                    auto_adjust=False,
                    prepost=False,
                )
                if intraday is None or intraday.empty:
                    continue
                px = _last_numeric(intraday.get("Close"))
                if px is None:
                    continue
                price = px
                try:
                    quote_at = intraday.index[-1].isoformat()
                except Exception:
                    pass
                quote_type = "LIVE"
                break
            except Exception:
                continue

    # Previous close must be the trading day before the quote day.
    if is_live:
        # Yahoo may or may not already include today's partial daily candle.
        if latest_date == now.date() and len(daily_rows) >= 2:
            prev_close = daily_rows[-2][1]
        else:
            prev_close = latest_close
    else:
        prev_close = daily_rows[-2][1] if len(daily_rows) >= 2 else None

    if prev_close is None or prev_close <= 0:
        change = None
        change_pct = None
    else:
        change = price - prev_close
        change_pct = (change / prev_close) * 100.0

    return {
        "symbol": "IHSG",
        "source_symbol": SYMBOL,
        "price": round(price, 2),
        "previous_close": round(prev_close, 2) if prev_close is not None else None,
        "change": round(change, 2) if change is not None else None,
        "change_pct": round(change_pct, 3) if change_pct is not None else None,
        "market_date": latest_date.isoformat() if latest_date else None,
        "quote_at": quote_at,
        "updated_at": now.isoformat(),
        "quote_type": quote_type,
        "market_state": state,
        "stale": False,
        "policy": "LIVE_WHEN_OPEN_LAST_CLOSE_WHEN_CLOSED",
    }


def main():
    market = idx_market_session()
    state = str(market.get("state") or "")
    print(f"HANZ IHSG SNAPSHOT | IDX={state}", flush=True)

    existing = _read_existing()
    try:
        payload = fetch_ihsg()
    except Exception as exc:
        # Never replace a valid last-known-good snapshot with zero/null.
        if float(existing.get("price") or 0) > 0:
            print(f"IHSG refresh failed; keeping last-known-good snapshot: {exc}", flush=True)
            return
        raise

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
