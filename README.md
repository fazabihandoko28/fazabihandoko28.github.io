# HANZ Intelligence v0.2

Evidence-first market intelligence foundation for BEI and ADX.

> **HANZ isn't loyal to stocks. HANZ is loyal to profits.**

## What v0.2 actually delivers

- vendor-independent market-data interface
- automatic symbol discovery from the connected provider
- OHLCV validation and quality gate
- deterministic technical evidence engine
- EMA20, EMA50, RSI14, ATR14, relative volume, support and resistance
- liquidity, extension-risk, and risk/reward proxy evidence
- integration with the v0.1 Disqualifier and Trade Permit Engine
- autonomous multi-symbol scanner
- JSON audit output
- unit tests

## What it does **not** claim yet

- no live licensed BEI feed
- no live licensed ADX feed
- no news, broker-flow, order-book, or whale identity feed
- no automated order execution
- no claim of profitability or predictive accuracy

## Repository layout

```text
src/hanz_core/       decision and disqualifier logic
src/hanz_data/       market-data contracts, CSV reference provider, validation
src/hanz_technical/  deterministic indicators and evidence generation
src/hanz_scanner/    autonomous universe scanning
src/hanz_app/        command-line entry point
tests/               repeatable tests
docs/                specifications and architecture
```

## Run all tests

```bash
python -m unittest discover -s tests -v
```

## Run a scan

Prepare folders such as:

```text
market_data/
  BEI/
    BBCA.csv
    BBRI.csv
  ADX/
    FAB.csv
```

Each CSV uses:

```text
datetime,open,high,low,close,volume
```

Then run:

```bash
PYTHONPATH=src python -m hanz_app.scan --data-root market_data --markets BEI ADX --output scan_result.json
```

The scanner discovers all symbols automatically. No ticker search is required.
