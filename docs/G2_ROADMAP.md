# HANZCUAN G2 — Trading Intelligence & Execution Readiness

Status: **PLANNED / NOT CERTIFIED**. This document registers the proposed G2 workstream; it does not activate trading or certify G1.

## Scope and ordered work

1. **P0 — Top 5 auto-replacement:** rank eligible candidates from the available universe using predeclared liquidity, risk, and signal-quality criteria. If fewer than five qualify, search remaining candidates; never fill slots with ineligible symbols. Freeze each selection before its OOS evaluation; never choose replacements using the same OOS outcomes.
2. **P0 — Point-in-time walk-forward OOS evidence:** produce traceable, chronological IS/OOS windows and genuine trade-level exports; run the existing validator with its unchanged minimums. Report insufficient evidence as UNVERIFIED, never PASS.
3. **P0 — Execution costs:** integrate actual, sourced fee and slippage assumptions into trade-level net-R evidence; preserve gross-to-net reconciliation and fail closed on invalid values.
4. **P1 — FAST intraday verification:** independently verify genuine session candles for at least **190 of 198** symbols. Outside the IDX regular session, report SKIPPED_MARKET_CLOSED / STALE, not a provider failure or a LIVE PASS.
5. **P1 — Risk and signal quality:** verify position sizing, stop-loss behavior, risk limits, signal consistency and no false BUY eligibility.
6. **P2 — Monitoring and end-to-end tests:** validate data ingestion, selection, scoring, cost calculations, OOS evidence, safety gating, and recovery together.

## Non-negotiable constraints

- **G0 stays CLOSED and immutable.** No G0 code, config, workflow, database, or PASS criteria changes.
- G2 is separate from G1. Existing unverified **G1 OOS and FAST LIVE** requirements remain unverified; moving work to G2 does not retroactively certify G1.
- Never fabricate market candles, transactions, returns, test results or certification.
- Preserve freshness, execution-risk, and BUY/trading safety gates; **190/198** remains fixed.
- Commit implementation only after genuine tests PASS, then read back and verify; record evidence and exceptions explicitly.
- Relax only noncritical research/process/milestone requirements, never safety gates.
- No live-trading activation or BUY permission is implied by this roadmap.

## Initial deliverables / acceptance evidence

| Workstream | Required evidence | Initial state |
| --- | --- | --- |
| Top 5 replacement | Deterministic ranking, fallback tests, frozen selection before OOS | NOT STARTED |
| Walk-forward OOS | Real point-in-time trades/windows and validator PASS | UNVERIFIED |
| Fees and slippage | Traceable assumptions, trade-level net-R and regression tests | INTEGRATION PENDING |
| FAST intraday | Genuine >=190/198 fresh bars during active IDX session | UNVERIFIED |
| Trading safety | Regression tests confirming gates remain locked without evidence | PENDING |
| End-to-end | Reproducible integration test and CI artifact | PENDING |

This is a planning document, **not a claim of implementation or PASS**.
