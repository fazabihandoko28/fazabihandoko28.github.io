# HANZ Intelligence — Session #002

## Delivered

1. Free delayed research connector using `yfinance`.
2. Explicit source policy: this feed is approved for paper trading only, never for live-money execution.
3. Configurable pilot universe. Commander does not enter tickers during each scan.
4. Scheduled GitHub Actions paper scan.
5. Persistent paper-trading journal with duplicate protection.
6. Audit output records source grade, delay status, evidence, vetoes, and signal price.

## Important limitation

`yfinance` is an open-source interface to Yahoo Finance public endpoints. It is not an official BEI or ADX feed and can have delays or coverage gaps. The code therefore labels it `YAHOO_FINANCE_RESEARCH_ONLY`, rejects it for live trading, and uses it only to prove the scanner and paper-trading workflow at zero cost.

BEI `.JK` pilot mappings are enabled. ADX rows remain disabled until each Yahoo ticker mapping has been independently verified. HANZ will not guess ADX symbols.

## Automated workflow

On weekdays after BEI close, GitHub Actions:

1. installs the project;
2. runs all unit tests;
3. fetches the enabled pilot universe;
4. validates and scans each series;
5. writes `artifacts/paper_scans/latest.json`;
6. appends new candidate signals to `artifacts/paper_trading/journal.json`;
7. uploads both files as a GitHub artifact;
8. commits the journal when new signals were added.

## Acceptance criteria

- No symbol is generated from invented data.
- Missing or failed symbols are recorded as errors without stopping the market scan.
- The research source cannot pass the live-trading source gate.
- Re-running the same signal does not duplicate the paper journal.
- The scan is reproducible from its audit output.
