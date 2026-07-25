# HANZ Intelligence v0.3

Evidence-first autonomous market data acquisition and decision foundation for BEI and ADX.

> HANZ isn't loyal to stocks. HANZ is loyal to profits.

## What v0.3 delivers

- automatic market symbol discovery through provider adapters
- provider registry for separate BEI and ADX data sources
- vendor-neutral REST/JSON market-data adapter
- bounded retries and request rate limiting
- market-symbol normalization
- validated file cache
- complete acquisition audit trail
- invalid-data rejection before analysis
- full-universe acquisition orchestration
- existing technical evidence, scanner, disqualifier, and trade-permit engines

## Important status

v0.3 is a production-quality acquisition framework, not yet a licensed live-feed connection. No credentials or paid-provider assumptions are committed. Live BEI/ADX operation begins only after a lawful provider is selected and its credentials are stored as cloud secrets.

## Tests

Run:

```bash
python -m unittest discover -s tests -v
```

## One-click repository update

Windows users can run `UPDATE_GITHUB_ONE_CLICK.bat`. The script clones or updates the private repository, copies this release, runs all tests, and pushes only when every test passes.

## v0.4 — Session #001 Market Scanner

This release adds a bounded, autonomous Market Scanner and free GitHub Actions workflow. It discovers symbols automatically, ranks by evidence dominance, returns no more than the configured candidate limit, and creates an auditable JSON paper-scan artifact. It does not fabricate candidates when verified data is unavailable.
