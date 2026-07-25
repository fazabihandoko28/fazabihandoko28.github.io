# HANZ Intelligence

Evidence-first market research and paper-trading system for BEI and ADX.

> **HANZ isn't loyal to stocks. HANZ is loyal to profits.**

## Current capabilities

- Validated OHLCV acquisition through provider adapters.
- Technical evidence generation.
- Hard disqualifier and Trade Permit decision engine.
- Autonomous multi-symbol market scanner.
- Automated paper-signal journal.
- Strict no-lookahead historical validation.
- GitHub Actions tests and research workflows.

## Safety boundary

The bundled Yahoo Finance connector is delayed and **research-only**. HANZ blocks it from live-money execution. Current outputs are evidence screening and historical/paper validation—not orders, forecasts, or profit guarantees.

## Install and test

```bash
python -m pip install -e .
python -m unittest discover -s tests -v
```

## Run paper scan

```bash
python -m hanz_app.paper_scan \
  --universe config/universe/pilot_universe.csv \
  --markets BEI \
  --output artifacts/paper_scans/latest.json
```

## Run no-lookahead historical validation

```bash
python -m hanz_app.validate_history \
  --universe config/universe/pilot_universe.csv \
  --markets BEI \
  --period 5y \
  --output artifacts/historical_validation/latest.json
```

The validation engine records the decision first using only visible historical bars, then reveals the next bars to measure the observed outcome.
