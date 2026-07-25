# HANZ Intelligence — Session #001 Market Scanner

## Implemented

- Automatic symbol discovery; no ticker input.
- Per-symbol data validation and fault isolation.
- Hard disqualification through the Core Decision Engine.
- Evidence summaries and auditable selection/rejection reasons.
- Deterministic evidence-dominance ranking rather than a displayed prediction score.
- Configurable candidate cap (default: five per market).
- Separate candidates, reviewed, rejected, and data-error outputs.
- JSON paper-scan audit report.
- GitHub Actions CI on push/pull request.
- Free scheduled paper-scan job that refuses to invent results when verified data is absent.

## Explicit limitations

This release does not claim live BEI/ADX coverage. The scheduled job only scans verified CSV files found under `data/live/BEI` and `data/live/ADX`. If none exist, it records `NO_VERIFIED_DATA` and produces no candidate.

## Definition of done result

- Universe discovery: implemented.
- Hard filter: implemented.
- Evidence collection: implemented.
- Candidate ranking: implemented and deterministic.
- Maximum candidate list: implemented.
- Selection and rejection reasons: implemented.
- Audit output: implemented.
- Automated tests and GitHub workflow: implemented.
