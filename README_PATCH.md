# HANZ v0.9 — Expanded BEI Pilot & Evidence Ranking

This patch expands the BEI paper-research universe from 10 to 30 symbols and improves the report without presenting a fake probability score.

## Visible changes

- Coverage percentage: how many symbols were actually analyzed.
- Color-first evidence matrix: Trend, Volume, Resistance, Risk/Reward, Liquidity, Extension.
- Evidence strength: STRONG, DEVELOPING, or WEAK.
- Actionable candidates remain limited and evidence-gated.
- A Top Developing Watchlist is shown when no READY candidate exists.
- Technical values are available for audit, while the main decision remains color/status based.

## Validation

- 32 unit tests passed.
- Repository audit passed.
- The feed remains delayed, research-only, and unsuitable for live-money execution.
