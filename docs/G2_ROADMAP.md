# HANZCUAN G2 — Trading Intelligence & Execution Readiness

Status: **G2 research/development regression verified (72/72 PASS); full development closure NOT YET ESTABLISHED. G2 trading certification OPEN.** The software test result is not a market-performance or execution authorization.

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

## Verified checkpoint (2026-11-22)

- Commit `07f1e1af86a94f24f5e8fd1d22289e4cfadec050`: [G2 regression](https://github.com/fazabihandoko28/fazabihandoko28.github.io/actions/runs/45035650374) **72/72 PASS**; [production read-only research workflow](https://github.com/fazabihandoko28/fazabihandoko28.github.io/actions/runs/45035650470) **SUCCESS**. These runs do not independently validate live trading or historical OOS.
- Production snapshot (latest `2026-11-20T19:07:33Z`): eligible **BJTM, EXCL, TBIG (3/5)**; removal of BJTM has **NO_ELIGIBLE_REPLACEMENT**. Research-only expanded list: **BJTM, EXCL, TBIG, AMRT, MIKA (5/5)**; research additions do not qualify for production BUY.
- Historical point-in-time OOS after costs: **UNVERIFIED**. FAST LIVE >=190/198 fresh independent bars: **UNVERIFIED**. Market-session freshness independently verified: **false**. `buy_authorized=false`.

## Closure rule — separate software from trading certification

- **G2 Development CLOSED** only after required implementation and end-to-end integration are demonstrated complete, and their regression/CI checks pass. The 72/72 G2 unit/integration tests establish the tested scope, **not** automatically every end-to-end requirement. Do not reopen completed development without a reproducible defect.
- **G2 Trading Certification CLOSED** only with independent real-market production Top 5 and actual replacement evidence, chronological point-in-time OOS trade records with verified costs, and FAST LIVE >=190/198 genuine fresh IDX-session bars, all meeting unchanged safety requirements. If missing, keep certification **OPEN** without relabeling it a software defect.
- Research relaxation can fill a **research** Top 5, never a production Top 5 or BUY gate. No automated trading.
- Next action must advance a missing evidence gate or repair a demonstrated defect; do not repeat speculative audits or silently loosen certification thresholds.

## Initial deliverables / acceptance evidence

| Workstream | Required evidence | Initial state |
| --- | --- | --- |
| Top 5 replacement | Deterministic ranking, fallback tests, frozen selection before OOS | NOT STARTED |
| Walk-forward OOS | Real point-in-time trades/windows and validator PASS | UNVERIFIED |
| Fees and slippage | Traceable assumptions, trade-level net-R and regression tests | INTEGRATION PENDING |
| FAST intraday | Genuine >=190/198 fresh bars during active IDX session | UNVERIFIED |
| Trading safety | Regression tests confirming gates remain locked without evidence | PENDING |
| End-to-end | Reproducible integration test and CI artifact | PENDING |

The initial-state table is historical planning context; the verified checkpoint above supersedes it for current status. No market certification or BUY permission is implied.
