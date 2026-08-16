import json
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf


UNIVERSE = Path("artifacts/universe/bei_top100.csv")
OUTPUT = Path("artifacts/health/intraday_health.json")

SAMPLE_SIZE = 20

TESTS = [
    {"interval": "5m", "period": "5d"},
    {"interval": "1m", "period": "1d"},
]


def utc_now():
    return datetime.now(timezone.utc)


def load_symbols():
    df = pd.read_csv(UNIVERSE)

    for col in ["symbol", "ticker", "code"]:
        if col in df.columns:
            symbols = df[col].dropna().astype(str).tolist()
            break
    else:
        symbols = df.iloc[:, 0].dropna().astype(str).tolist()

    return symbols[:SAMPLE_SIZE]


def test_symbol(symbol, interval, period):
    started = time.time()

    try:
        df = yf.download(
            symbol,
            period=period,
            interval=interval,
            progress=False,
            auto_adjust=False,
            threads=False,
        )

        latency = round(time.time() - started, 2)

        if df.empty:
            return {
                "symbol": symbol,
                "ok": False,
                "reason": "empty_data",
                "latency_sec": latency,
            }

        last_ts = df.index[-1]

        if getattr(last_ts, "tzinfo", None) is None:
            last_ts = last_ts.tz_localize("UTC")
        else:
            last_ts = last_ts.tz_convert("UTC")

        age_minutes = (
            utc_now() - last_ts.to_pydatetime()
        ).total_seconds() / 60

        return {
            "symbol": symbol,
            "ok": True,
            "rows": len(df),
            "last_bar_utc": last_ts.isoformat(),
            "age_minutes": round(age_minutes, 1),
            "latency_sec": latency,
        }

    except Exception as exc:
        return {
            "symbol": symbol,
            "ok": False,
            "reason": str(exc),
            "latency_sec": round(time.time() - started, 2),
        }


def run_test(interval, period, symbols):
    results = []

    for symbol in symbols:
        print(f"Testing {symbol} {interval}...", flush=True)
        results.append(
            test_symbol(symbol, interval, period)
        )

    successful = [x for x in results if x["ok"]]

    success_rate = (
        len(successful) / len(results) * 100
        if results else 0
    )

    avg_latency = (
        sum(x["latency_sec"] for x in results) / len(results)
        if results else 0
    )

    return {
        "interval": interval,
        "period": period,
        "symbols_tested": len(results),
        "success_count": len(successful),
        "success_rate_pct": round(success_rate, 1),
        "avg_latency_sec": round(avg_latency, 2),
        "results": results,
    }


def main():
    symbols = load_symbols()

    report = {
        "tested_at": utc_now().isoformat(),
        "sample_size": len(symbols),
        "tests": [],
    }

    for test in TESTS:
        report["tests"].append(
            run_test(
                test["interval"],
                test["period"],
                symbols,
            )
        )

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print("\n========== INTRADAY HEALTH ==========")

    for test in report["tests"]:
        print(
            f"{test['interval']} | "
            f"success={test['success_rate_pct']}% | "
            f"avg latency={test['avg_latency_sec']}s"
        )

    print(f"Report written to {OUTPUT}")


if __name__ == "__main__":
    main()
