# HANZ Intelligence v0.5 — Session #002

Evidence-first market scanner for BEI and ADX, now with a zero-cost delayed research connector and automated paper-trading journal.

## Run tests

```bash
python -m pip install -e .
python -m unittest discover -s tests -v
```

## Run a free paper scan

```bash
python -m hanz_app.paper_scan \
  --universe config/universe/pilot_universe.csv \
  --markets BEI ADX \
  --output artifacts/paper_scans/latest.json

python -m hanz_app.update_journal
```

## Safety boundary

The included Yahoo/yfinance source is **research and paper-trading only**. It is deliberately rejected for live-money execution. BEI pilot mappings are enabled; ADX mappings remain disabled until verified.
