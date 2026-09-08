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


def fetch_ihsg():
    ticker = yf.Ticker(SYMBOL)

    daily = ticker.history(period="7d", interval="1d", auto_adjust=False)
    closes = daily.get("Close") if daily is not None and not daily.empty else None
    daily_values = []
    if closes is not None:
        try:
            daily_values = [float(v) for v in closes.dropna().tolist()]
        except Exception:
            daily_values = []

    prev_close = daily_values[-2] if len(daily_values) >= 2 else (daily_values[-1] if daily_values else None)

    live_price = None
    live_at = None
    for interval, period in (("1m", "1d"), ("2m", "5d"), ("5m", "5d")):
        try:
            intraday = ticker.history(period=period, interval=interval, auto_adjust=False, prepost=False)
            if intraday is None or intraday.empty:
                continue
            px = _last_numeric(intraday.get("Close"))
            if px is None:
                continue
            live_price = px
            try:
                live_at = intraday.index[-1].isoformat()
            except Exception:
                live_at = None
            break
        except Exception:
            continue

    if live_price is None:
        if daily_values:
            live_price = daily_values[-1]
        else:
            raise RuntimeError("IHSG quote unavailable")

    if prev_close is None or prev_close <= 0:
        change = None
        change_pct = None
    else:
        change = live_price - prev_close
        change_pct = (change / prev_close) * 100.0

    return {
        "symbol": "IHSG",
        "source_symbol": SYMBOL,
        "price": round(live_price, 2),
        "previous_close": round(prev_close, 2) if prev_close is not None else None,
        "change": round(change, 2) if change is not None else None,
        "change_pct": round(change_pct, 3) if change_pct is not None else None,
        "quote_at": live_at,
        "updated_at": jakarta_now().isoformat(),
        "policy": "REFRESH_ONLY_DURING_IDX_OPEN",
    }


def main():
    market = idx_market_session()
    state = str(market.get("state") or "")
    print(f"HANZ IHSG SNAPSHOT | IDX={state}", flush=True)

    if not market.get("is_trading_day") or state not in {"SESSION_1", "SESSION_2"}:
        print("IHSG snapshot skipped: IDX is not actively trading.", flush=True)
        return

    payload = fetch_ihsg()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
