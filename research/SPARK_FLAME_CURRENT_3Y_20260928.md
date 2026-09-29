# Three-year Spark and Flame replay — running

Baseline: AlphaGEX `3637fd18396b9ab532ee0d9bd42281338353a8a2` (September 28, 2026).
Window: September 29, 2023–September 28, 2026; 751 regular or half-day sessions.
Separate accounts: Flame $2,000; Spark $5,000. No subsequent deposits.

## Profiles

1. Current customer package: 20% base sizing; N=3/K=.10 variant-G floor;
   $50 margin; pre-trigger calm +1; post-trigger calm +1 subject to $4,000
   deposit minimum; customer FLINT netted against actual/planned host risk.
2. Internal ONE_STRATEGY: identical pure sizing functions plus internal
   liquidity caps and the literal current internal FLINT planning caller.
3. Legacy high-water dollar-rung ladder, FLINT and Flame favorable upsize.
4. Legacy profit ladder plus per-bot fast-start rules and FLINT.

These are SEPARATE profiles. The superseded dollar-rung ladder is not stacked
on top of the September 28 customer sizing package.

Each profile runs natural bid/ask and 3-cent adverse entry/close cases.
FLINT and XSP routing are enabled. Missing XSP quotes use the source's SPY
fallback. An accepted XSP swap without authentic SPX settlement is unresolved.
Main default profit target and conventional stop are disabled. Put/call
assignment-guard buffers are $.50/$.25, checked during the final three minutes
before the actual close. Entries retry within the source-default bot windows.
Source defaults are frozen; account-specific DB overrides are not applied.

## Data and execution boundaries

The private ThetaData proxy supplies SPY minute bars, official daily closes,
and historical option bid/ask/depth. Stock minute OPEN is the contemporaneous
spot proxy; quote snapshots are not verified broker executions. Spread prices
use sell-bid/buy-ask with checks on the required execution sides. A zero-bid
long contributes zero sale proceeds at buyback; its zero bid size does not
invalidate the short option's valid ask. Positive long bids require size. Fees are $1.40 per spread,
with $50 monthly subscription reported externally over 36 billing cycles.

Historical gamma now uses a uniform reconstruction across the requested window,
including 20 pre-window warmup sessions. Inputs are historical ThetaData closing
chains from the prior session, morning OI (reported as the prior session's
closing OI), and SPY spot at 11:05 ET. The once-per-day shared gamma context
mirrors the scanner's morning Spark evaluation before Flame.

For each 0..60 DTE contract, infer prior-close IV from quote mids using
Black-Scholes (r=.045, q=.012), then recompute gamma at the entry time and spot.
Apply gamma × OI × 100 × spot² × .01, summed separately over calls and puts.
Missing/unusable contract IV is reconstructed from the same-expiry, same-side
prior IV curve: interpolate variance between strikes and use flat endpoint IV
outside its observed wings. Counts of interpolated/extrapolated contracts are
reported. An entirely missing expiry surface fails the day; it is not guessed.
Time-to-expiry uses actual half-day closes, with a five-minute lower bound.

The native p67 / 20-session upsizing function compares this reconstruction
against its own trailing values. No Tradier observations are spliced into the
modelled series. This validates the modelled historical hypothesis; it does not
prove exact agreement with historical Tradier Greeks or broker executions.
The full-feature exact-validation flag remains false for that reason.

The existing long net-gamma baseline lives in SpreadWorks; it is not used as a
replacement for FLINT's call-side gamma input. XSP historical quotes are read
per selected contract; settlement uses the CBOE SPX history CSV's SPX column /10.
Explicit provider no-observation responses are recorded as quote absences.

The event blackout master is disabled in frozen source. Historical NYSE
closures include January 9, 2025, independently of the source's limited
2025–2027 calendar. Flame's afternoon entries skip half days; Spark's morning
entry remains eligible and its guard uses the early close.

The collector retries failed requests, stops after three consecutive session
failures, restores account state on a failed day, and invalidates account paths
with missing payoff data. Partial paths cannot be presented as complete.
Intraday mark gaps are counted; marked drawdown is an observed bound when
coverage is incomplete.

## Verification completed

- Pure-function boundary checks: sizing, calm add-on, floor/cushion, guard
  costs, CSV decoding, timezone conversion, holiday exclusions.
- Synthetic integration: 16 account paths, scaled P&L and fees, adverse fills,
  XSP fallback, no orders. This is NOT a market-performance result.
- Node syntax and whitespace checks.

## Execution

Node 24.19.0. The isolated checkpoint store uses pinned pg 8.16.3; no broker SDK is loaded.

```sh
node research/spark_flame_current_3y_20260928.cjs --self-test
node research/spark_flame_current_3y_20260928.test.cjs
node research/spark_flame_current_3y_20260928.cjs
```

The remote job needs `THETADATA_BASE_URL=http://thetadata-proxy:10000` in the
same Render region/network. All status/result endpoints require the
`RESEARCH_ACCESS_TOKEN` bearer token. Only `/health` is unauthenticated and
contains no strategy, progress, or results.

Checkpoints are gzip-compressed state in the isolated alphagex_backtest database,
in spark_flame_research_checkpoints. The connection is an environment secret.
The job verifies the database name before creating or writing that research table.
Keys include the run ID and both research source hashes, so a changed version
cannot reuse an old performance result. A restart resumes the same fresh run;
completed results stay retrievable after an idle restart. Raw CSV files remain
process-local; their scope, retrieval timestamp and SHA-256 hashes are retained.
Reports and trades are also exported by the read-only observer. No live trading code, customer
balances, credentials, kill switches, or production database schemas change.

## Current status

User approved the authenticated free research service on September 29, 2026.
The runner is deployed and processing real historical sessions. Performance
results are pending; partial exports are not validated three-year returns.

Service: https://dashboard.render.com/web/srv-dau3ni7lot8c739htsv0
Execution branch: `research/spark-flame-current-3y-20260928`.
Latest runner/test commit: `acabd20863b48f119a1504f6dd13b94369e9a1c0`.

A read-only observer polls authenticated status every 45 seconds and saves
existing report/trade/daily exports every five minutes. Quotes retrieved
within this run are reused for later scanner minutes of the same contract.
The collector requests historical market data only and never sends orders.

Regular-session stock bars exclude intervals starting at the market close.
Expiry settlement uses the independently retrieved official daily close;
empty post-close OHLC records do not invalidate prior session trades.

Verification: the independent CBOE SPX settlement series contains every one of
this replay's 751 requested sessions. Contract-level XSP quote availability
is checked during execution; missing observations follow the native SPY fallback.
