# HANZ Intelligence v0.2 Architecture

## Scope delivered

1. **Provider abstraction** — analysis code is independent from any data vendor.
2. **Automatic symbol discovery** — the scanner obtains the market universe from the provider; Commander does not enter ticker codes.
3. **Data-quality gate** — malformed, duplicated, stale, or insufficient data cannot silently become a trade signal.
4. **Technical Evidence Engine** — deterministic EMA, RSI, ATR, relative volume, support, resistance, liquidity proxy, and extension checks.
5. **Core integration** — all evidence is passed into the existing Disqualifier and Trade Permit Engine.
6. **Fault isolation** — one bad symbol cannot stop the market scan.
7. **Audit output** — each decision contains evidence source, timestamp, and calculation detail.

## Important limitation

v0.2 does not claim live BEI or ADX connectivity. A licensed or otherwise authorized market-data provider must implement the `MarketDataProvider` contract. The included directory-CSV provider is the reference implementation and test harness.

## Next engineering milestone

- authorized BEI provider adapter
- authorized ADX provider adapter
- market-index regime adapter
- historical corporate-action normalization
- news evidence adapter
