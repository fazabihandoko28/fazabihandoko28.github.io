# HANZ Dynamic Top-100 BEI Universe

The paper-scan workflow now builds the BEI universe before every scan instead of trusting a fixed 100-stock list.

Candidate pool: `config/universe/bei_candidate_pool.csv` (170 BEI tickers).
Generated universe: `artifacts/universe/bei_top100.csv`.
Audit metrics: `artifacts/universe/bei_liquidity_metrics.json`.

Anti-sleep gates (last 60 trading observations):
- at least 45 observations
- active (non-zero volume) on >= 85% of days
- median daily traded value >= IDR 1 billion
- median volume >= 100,000 shares/day
- meaningful movement (absolute daily return >= 0.25%) on >= 15% of observations
- last close >= IDR 50

Eligible shares are ranked primarily by traded value, with activity, movement and volume also contributing. HANZ selects the top 100. If fewer than 100 pass the gates, the workflow fails rather than padding the universe with sleeping/illiquid shares.
