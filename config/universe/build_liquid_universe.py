from __future__ import annotations

import argparse
import csv
import json
import math
from dataclasses import dataclass, asdict
from pathlib import Path

import pandas as pd


@dataclass(frozen=True)
class LiquidityMetric:
    market: str
    symbol: str
    yahoo_ticker: str
    sector: str
    observations: int
    active_ratio: float
    avg_daily_value: float
    median_daily_value: float
    median_volume: float
    movement_ratio: float
    last_close: float
    score: float
    eligible: bool
    rejection_reason: str = ""


def load_pool(path: str | Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            market = (row.get("market") or "").strip().upper()
            symbol = (row.get("symbol") or "").strip().upper()
            ticker = (row.get("yahoo_ticker") or "").strip()
            enabled = (row.get("enabled") or "true").strip().lower() not in {"0", "false", "no"}
            if enabled and market == "BEI" and symbol and ticker:
                rows.append({
                    "market": market,
                    "symbol": symbol,
                    "yahoo_ticker": ticker,
                    "sector": (row.get("sector") or "").strip(),
                })
    if not rows:
        raise ValueError("Candidate pool contains no enabled BEI symbols")
    return rows


def _ticker_frame(downloaded: pd.DataFrame, ticker: str, ticker_count: int) -> pd.DataFrame:
    if downloaded is None or downloaded.empty:
        return pd.DataFrame()
    if ticker_count == 1:
        return downloaded.copy()
    if isinstance(downloaded.columns, pd.MultiIndex):
        # yfinance may return either (Price, Ticker) or (Ticker, Price).
        level0 = set(map(str, downloaded.columns.get_level_values(0)))
        level1 = set(map(str, downloaded.columns.get_level_values(1)))
        if ticker in level0:
            return downloaded[ticker].copy()
        if ticker in level1:
            return downloaded.xs(ticker, axis=1, level=1).copy()
    return pd.DataFrame()


def evaluate(row: dict[str, str], frame: pd.DataFrame, lookback: int) -> LiquidityMetric:
    symbol, ticker = row["symbol"], row["yahoo_ticker"]
    if frame.empty or "Close" not in frame or "Volume" not in frame:
        return LiquidityMetric("BEI", symbol, ticker, row["sector"], 0, 0, 0, 0, 0, 0, 0, -1e9, False, "NO_DATA")

    data = frame[["Close", "Volume"]].copy().dropna(subset=["Close"])
    data = data.tail(lookback)
    if data.empty:
        return LiquidityMetric("BEI", symbol, ticker, row["sector"], 0, 0, 0, 0, 0, 0, 0, -1e9, False, "NO_DATA")

    close = pd.to_numeric(data["Close"], errors="coerce")
    volume = pd.to_numeric(data["Volume"], errors="coerce").fillna(0.0)
    valid = close.notna() & (close > 0)
    close, volume = close[valid], volume[valid]
    observations = int(len(close))
    if observations == 0:
        return LiquidityMetric("BEI", symbol, ticker, row["sector"], 0, 0, 0, 0, 0, 0, 0, -1e9, False, "NO_DATA")

    value = close * volume
    active_ratio = float((volume > 0).mean())
    returns = close.pct_change().abs()
    movement_ratio = float((returns >= 0.0025).mean()) if observations > 1 else 0.0
    avg_value = float(value.mean())
    median_value = float(value.median())
    median_volume = float(volume.median())
    last_close = float(close.iloc[-1])

    reasons = []
    if observations < min(45, lookback): reasons.append("SHORT_HISTORY")
    if active_ratio < 0.85: reasons.append("TOO_MANY_ZERO_VOLUME_DAYS")
    if median_value < 1_000_000_000: reasons.append("LOW_TRADED_VALUE")
    if median_volume < 100_000: reasons.append("LOW_VOLUME")
    if movement_ratio < 0.15: reasons.append("TOO_STATIC")
    if last_close < 50: reasons.append("PRICE_TOO_LOW")
    eligible = not reasons

    # Liquidity dominates; activity and actual price movement prevent 'sleeping' shares.
    score = (
        55.0 * math.log10(max(avg_value, 1.0))
        + 20.0 * active_ratio
        + 15.0 * movement_ratio
        + 10.0 * math.log10(max(median_volume, 1.0))
    )
    return LiquidityMetric(
        "BEI", symbol, ticker, row["sector"], observations,
        round(active_ratio, 4), round(avg_value, 2), round(median_value, 2),
        round(median_volume, 2), round(movement_ratio, 4), round(last_close, 4),
        round(score, 4), eligible, ";".join(reasons),
    )


def build(pool: list[dict[str, str]], *, target: int, period: str, lookback: int) -> tuple[list[LiquidityMetric], list[LiquidityMetric]]:
    import yfinance as yf

    tickers = [r["yahoo_ticker"] for r in pool]
    downloaded = yf.download(
        tickers=tickers,
        period=period,
        interval="1d",
        auto_adjust=False,
        progress=False,
        threads=True,
        group_by="column",
        timeout=30,
    )
    metrics = [evaluate(row, _ticker_frame(downloaded, row["yahoo_ticker"], len(tickers)), lookback) for row in pool]
    eligible = sorted((m for m in metrics if m.eligible), key=lambda m: m.score, reverse=True)
    selected = eligible[:target]
    return selected, metrics


def write_universe(selected: list[LiquidityMetric], path: str | Path) -> None:
    output = Path(path); output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["market", "symbol", "yahoo_ticker", "enabled", "sector", "notes"])
        for rank, item in enumerate(selected, start=1):
            writer.writerow([item.market, item.symbol, item.yahoo_ticker, "true", item.sector,
                             f"Dynamic liquid rank {rank}; score={item.score}; median_value={item.median_daily_value:.0f}"])


def main() -> int:
    parser = argparse.ArgumentParser(description="Build dynamic Top-N liquid/tradeable BEI universe")
    parser.add_argument("--pool", default="config/universe/bei_candidate_pool.csv")
    parser.add_argument("--output", default="artifacts/universe/bei_top100.csv")
    parser.add_argument("--metrics", default="artifacts/universe/bei_liquidity_metrics.json")
    parser.add_argument("--target", type=int, default=100)
    parser.add_argument("--period", default="6mo")
    parser.add_argument("--lookback", type=int, default=60)
    args = parser.parse_args()

    pool = load_pool(args.pool)
    selected, metrics = build(pool, target=args.target, period=args.period, lookback=args.lookback)
    if len(selected) < args.target:
        raise SystemExit(
            f"Only {len(selected)} BEI shares passed anti-sleep/liquidity gates; target={args.target}. "
            "HANZ refuses to pad the universe with illiquid/static shares. Expand the candidate pool instead."
        )
    write_universe(selected, args.output)
    metrics_path = Path(args.metrics); metrics_path.parent.mkdir(parents=True, exist_ok=True)
    metrics_path.write_text(json.dumps({
        "target": args.target,
        "selected_count": len(selected),
        "pool_count": len(pool),
        "rules": {
            "min_observations": min(45, args.lookback),
            "min_active_ratio": 0.85,
            "min_median_daily_value_idr": 1_000_000_000,
            "min_median_volume_shares": 100_000,
            "min_movement_ratio_abs_return_0_25pct": 0.15,
            "min_last_close": 50,
        },
        "selected": [asdict(x) for x in selected],
        "all_metrics": [asdict(x) for x in metrics],
    }, indent=2), encoding="utf-8")
    print(f"Dynamic BEI universe: selected {len(selected)} of {len(pool)} candidates -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
