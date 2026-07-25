# Changelog

All notable changes to HANZ Intelligence are recorded here.

## [0.6.0] - 2026-07-25

### Added
- Strict no-lookahead walk-forward historical validation engine.
- Auditable target-first, stop-first, ambiguous, and unresolved outcome classification.
- Historical validation CLI for the free research universe.
- Historical validation artifact workflow.

### Changed
- Repository documentation consolidated into stable architecture documents and this changelog.
- Version raised to 0.6.0.

### Removed
- Session-specific markdown files that duplicated release history.
- Python cache files from release artifacts.

## [0.5.0]

### Added
- Free research-only Yahoo Finance connector.
- Automated paper scan and paper journal.

## [0.4.0]

### Added
- Autonomous market scanner and candidate ranking.

## [0.3.0]

### Added
- Data acquisition framework, provider registry, retry, cache, and validation.

## [0.2.0]

### Added
- Technical evidence engine.

## [0.1.0]

### Added
- Core decision and disqualifier engine.

## 0.6.1 - Audit Fix

### Fixed
- Standardized test imports through `tests/bootstrap.py` so the suite runs
  directly from a fresh checkout without requiring `PYTHONPATH=src`.
- Removed generated Python cache files from the release package.

### Added
- `tools/audit_repository.py` for source compilation, unit-test, CI workflow,
  and repository-hygiene checks.
- CI repository-audit step.
- `.gitignore` rules for generated and secret files.

### Validation scope
- This release validates software structure and deterministic unit behavior.
- It does **not** validate market profitability or live-data accuracy.

## v0.8.0 — Pilot Data Recovery

- Added automatic Yahoo Chart fallback when yfinance fails or returns malformed/empty rows.
- Added compatibility for recent yfinance MultiIndex/Series-shaped OHLCV output.
- Disabled yfinance repair mode by default for more stable Jakarta ticker downloads.
- Added detailed per-symbol acquisition errors to the Alpha dashboard.
- Added test coverage for the fallback acquisition path.
