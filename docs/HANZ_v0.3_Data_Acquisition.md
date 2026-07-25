# HANZ Intelligence v0.3 — Data Acquisition Engine

## Purpose

Remove manual CSV handling from the Commander workflow. The acquisition boundary is responsible for fetching, normalizing, validating, caching, and auditing market data before any intelligence engine can consume it.

## Hard rule

Invalid, stale, malformed, duplicated, or insufficient market data is rejected before analysis. A provider failure produces an auditable failure result, never an invented value.

## Components

- `ProviderRegistry`: selects the configured provider per market.
- `HttpJsonProvider`: vendor-neutral REST adapter.
- `SymbolNormalizer`: converts Commander symbols to provider symbols through configuration.
- `RateLimiter`: prevents request bursts.
- `execute_with_retry`: bounded exponential retry.
- `FileSeriesCache`: transparent cache; cached data is revalidated.
- `AcquisitionService`: fetch → validate → cache → audit.
- `UniverseAcquirer`: discovers all symbols and acquires a complete market universe.

## Production provider status

The code now supports real REST providers, but no BEI or ADX commercial credential is embedded. Provider credentials must be supplied through deployment secrets, never committed to GitHub.

## Commander workflow

None. Once deployed and configured, acquisition runs from the server. The Commander only receives accepted intelligence outputs.
