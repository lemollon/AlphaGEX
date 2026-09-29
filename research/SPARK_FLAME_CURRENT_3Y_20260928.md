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

Authentic Tradier-source gamma context is only available starting September
28, 2026. The 20-session gamma-upsize gate executes, but historical add-on
performance cannot be validated from the currently available records.
No gamma values are fabricated or reconstructed with an incompatible source.
The full-feature validation flag therefore remains false even when the
covered-market-data replay completes.

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

Node 24.19.0. No external Node packages.

```sh
node research/spark_flame_current_3y_20260928.cjs --self-test
node research/spark_flame_current_3y_20260928.test.cjs
node research/spark_flame_current_3y_20260928.cjs
```

The remote job needs `THETADATA_BASE_URL=http://thetadata-proxy:10000` in the
same Render region/network. All status/result endpoints require the
`RESEARCH_ACCESS_TOKEN` bearer token. Only `/health` is unauthenticated and
contains no strategy, progress, or results.

Results/checkpoints are research-process files and structured Render log
records. They must be exported after execution; a free service filesystem is
not durable across replacement/restarts. No live trading code, customer
balances, credentials, kill switches, or production database schemas change.

## Current status

User approved the authenticated free research service on September 29, 2026.
The runner is deployed and processing real historical sessions. Performance
results are pending; partial exports are not validated three-year returns.

Service: https://dashboard.render.com/web/srv-dau3ni7lot8c739htsv0
Execution branch: `research/spark-flame-current-3y-20260928`.
Latest runner/test commit: `90a4f08965f9cbd9148fc09a21b59ebe35b85451`.

A read-only observer polls authenticated status every 45 seconds and saves
existing report/trade/daily exports every five minutes. Quotes retrieved
within this run are reused for later scanner minutes of the same contract.
The collector requests historical market data only and never sends orders.
