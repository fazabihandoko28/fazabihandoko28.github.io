# HANZ Intelligence v0.1

Core decision framework for BEI and ADX market intelligence.

## Principles
- No guessing
- Evidence first
- Capital protection first
- Commander does not search tickers
- Output is simple: READY, WAIT, HIGH_RISK, REJECT, HOLD, PREPARE_EXIT, EXIT

## What is included
- Core specification
- Deterministic evidence model
- Disqualifier engine
- Trade permit engine
- Audit trail
- Unit tests

## What is not included yet
- Live BEI/ADX feeds
- News ingestion
- Broker/order-book data
- Automated execution

## Run tests
```bash
python -m unittest discover -s tests -v
```
