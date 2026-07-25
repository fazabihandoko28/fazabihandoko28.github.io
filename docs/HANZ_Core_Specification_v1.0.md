# HANZ Intelligence Core Specification v1.0

## 1. Purpose
HANZ Intelligence is a market decision-support system for BEI and ADX. It performs the analysis; the Commander receives only concise instructions. The system must never invent missing facts.

## 2. Non-negotiable commitments
1. No guessing, assumptions, or unsupported speculation.
2. Every instruction must be traceable to timestamped evidence.
3. Missing critical evidence results in WAIT, not forced certainty.
4. Capital protection takes priority over trade frequency.
5. The same engine supports BEI and ADX through market adapters.
6. No automated order execution in the initial production scope.

## 3. Commander-facing statuses
### Entry
- READY: evidence supports entry and no hard veto is active.
- WAIT: setup is incomplete, conflicting, or data is insufficient.
- HIGH_RISK: momentum exists but execution risk is elevated.
- REJECT: one or more hard disqualifiers are active.

### Position management
- HOLD: continuation evidence remains intact.
- PREPARE_EXIT: momentum weakens or resistance/distribution risk rises.
- EXIT: invalidation, support failure, or hard risk event is confirmed.

## 4. Evidence hierarchy
1. Official exchange/company disclosure
2. Licensed market data
3. Derived quantitative indicators
4. Historical behaviour and pattern matching
5. Media/sentiment signals

Lower-level evidence can support but cannot overrule contradictory higher-level evidence.

## 5. Required evidence groups
- Market regime
- Liquidity and execution quality
- Price structure
- Volume confirmation
- Resistance/support map
- Historical behaviour
- News/catalyst, when relevant
- Money-flow/large-player footprint, when available
- Risk/invalidation

## 6. Hard disqualifiers
Any active hard disqualifier blocks READY:
- stale or incomplete market data
- liquidity below market-specific minimum
- spread above market-specific maximum
- confirmed support/invalidation break
- unresolved corporate halt/suspension
- price materially extended beyond permitted entry zone
- risk/reward below configured minimum
- contradictory official disclosure

## 7. Adaptive rules
Rules vary by:
- market: BEI or ADX
- instrument liquidity profile
- strategy: scalping or swing
- market regime: trending, sideways, stressed, recovery
- stock DNA: false-breakout tendency, reaction speed, normal pullback, news sensitivity

## 8. Decision sequence
1. Validate data freshness and completeness.
2. Apply hard disqualifiers.
3. Classify market regime.
4. Evaluate price/volume/liquidity.
5. Evaluate resistance and invalidation.
6. Evaluate historical behaviour.
7. Add catalyst and money-flow evidence.
8. Detect contradictions.
9. Produce status and concise reason.
10. Store full audit trail.

## 9. No-ticker-search workflow
Before market open and continuously during market hours, market adapters scan the eligible universe. Commander receives ranked opportunities and exit warnings without manually searching symbols.

## 10. Validation gates
An engine is not production-ready until it passes:
- unit tests
- indicator parity test against a trusted reference
- no-look-ahead historical replay
- blind backtest including fees/slippage
- live paper-trading period
- audit review of failures

## 11. Accuracy language
HANZ must never claim guaranteed prediction accuracy. It reports evidence completeness and status. Quantitative performance metrics remain available only in audit/validation views.

## 12. Initial acceptance criteria
- deterministic output for identical evidence
- every status contains machine-readable reasons
- no READY when a hard veto is active
- missing critical data cannot produce READY
- full decision is reproducible from stored evidence
